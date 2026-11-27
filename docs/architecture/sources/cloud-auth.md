# Signing in to a connection: TLS, client certificates, issued secrets

For changing how a server source encrypts its connection, which certificate it
trusts or offers, a person's cloud accounts, and how a password is issued by a
cloud or fetched from a secret store for every new connection.

Decisions here: D446, D447, D448, D449, D450, D451, D452, D453, D454, D455, D456, D461.

## D446. One TLS block, every server source

`app/adapters/tls.py` declares the block once, without a driver, and each
source's base model inherits it: PostgreSQL and TimescaleDB, MySQL and
MariaDB, ClickHouse, Redis, MongoDB, Cassandra and ScyllaDB, ZooKeeper, Kafka
and RabbitMQ.

- `tls_mode`: `disabled`, `preferred` (PostgreSQL and MySQL only: encrypted
  when the server offers it, nothing verified, plain text when it does not),
  `required` (encrypted, nothing verified), `verify_ca` (the chain, not the
  name), `verify_full` (the chain and the name).
- `tls_trust`: `system`, `certificate` (the PEM in `tls_ca_certificate`), or
  `amazon_rds` where RDS or DocumentDB can be on the other end (PostgreSQL,
  MySQL, MongoDB): `adapters/authorities/amazon-rds.pem`, every region's root
  from Amazon's global bundle of 2026-11-22 without Beta, Preview or expired
  roots — 108 certificates, 165 KB. No system store holds them.
- `tls_client_certificate` (PEM, not secret), `tls_client_key` and
  `tls_client_key_passphrase` (`SecretStr`, so D4 encrypts them).
- The fields are flat (D16) and go on a page of the connection window of
  their own, "TLS" (`layout(group="tls")`), so the address and the choice of
  method stay together on the first page. Each mode and trust is offered by
  `x-ui-choices` with a title.
- Every PEM is rewrapped as Docker's form already did (D418, the second use,
  now shared): a one-line secret box drops line breaks. An encrypted key is
  opened by its passphrase once, while the form validates, so a wrong one is
  refused there, and every driver and program is handed the opened key.
- An edit keeps a stored secret when its box is left empty, so the key cannot
  be emptied by hand: emptying the certificate takes the key and passphrase
  with it. A passphrase left from an earlier key is ignored by a plain one.
- What each driver is told:

| Driver | How |
| --- | --- |
| libpq | `sslmode`, `sslrootcert` (`system` or a file), `sslcert`, `sslkey` |
| aiomysql | an `SSLContext`; `preferred` keeps the old unverified context, and anything stricter is refused when the server offered no TLS |
| httpx (ClickHouse, RabbitMQ's API) | `verify=` the context |
| redis-py | a `Connection` subclass that puts the context into `open_connection` |
| pymongo | `tls`, `tlsAllowInvalidCertificates` or `tlsAllowInvalidHostnames`, `tlsCAFile`, `tlsCertificateKeyFile` |
| scylla-driver, aio-pika | the context |
| kazoo | `use_ssl`, `verify_certs`, `check_hostname`, `ca`, `certfile`, `keyfile` |
| librdkafka | `enable.ssl.certificate.verification`, `ssl.endpoint.identification.algorithm`, the PEMs inline |

- Programs run in a container — `psql` and `pg_dump`, `mysqldump` and the
  MariaDB client, the ClickHouse backup script, `redis-cli`, `mongosh` and
  `mongodump`, `cqlsh`, `zkCli.sh`, Kafka's tools, `rabbitmqadmin` — get the
  same mode, and the PEMs through `tls.with_program_files`: the variables are
  written to `/tmp/dp-tls` under `umask 077` by the program's shell and unset
  before it starts, so no PEM is an argument.
- **Existing rows behave exactly as before.** PostgreSQL's and MySQL's default
  is `preferred`, what libpq and MySQL's context did without a choice. The six
  sources that had a switch were migrated by `d7e2f9a4c1b8`, its statement
  named and run against old rows by a test: `true` became `verify_full`, or
  `verify_ca` for ZooKeeper, whose client never checked the name; a Kafka or
  RabbitMQ CA certificate became `tls_trust = certificate`.
- Redis does TLS, and a `rediss://` address is read as `verify_full` (D15's
  refusal is gone). A Redis password variant names an ACL user, `default` when
  empty, as `redis://user@host` shows.
- libpq's TLS failures are said as what to check — no TLS offered, the
  certificate not verified, a certificate for another name, a handshake that
  failed — and a missing client certificate is an authentication failure.

Known deviations:

- **MySQL's `required` is enforced after the handshake.** aiomysql goes on in
  plain text when the server offers no TLS; the refusal comes once the
  connection is open, by which time the server has seen a scramble of the
  password, never the password itself.
- **MariaDB's client checks the name whenever it checks at all.** A backup or
  restore of a MariaDB connection at `verify_ca` verifies the name too.
- **Some programs cannot leave a certificate unchecked.** `zkCli.sh` and
  Kafka's Java tools refuse `required` with a sentence naming the verifying
  modes; `redis-cli` and `rabbitmqadmin` cannot tell `verify_ca` from
  `verify_full` and check the name.
- **Only PostgreSQL and Redis are proven against a server here.** `pg-tls`
  accepts only TLS, a client certificate for `certuser` and passwords for the
  rest; `redis-tls` speaks only TLS with the ACL user `reader`. The other
  sources are proven by what their drivers are handed, not by a TLS server.
- **The downgrade is lossy.** It turns the mode back into a switch, drops a
  client certificate and leaves the new secrets in the encrypted blob, which
  older code reads only where its model ignores unknown keys.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D447. Key material on disk is private and short-lived

Where a driver reads a PEM only from a file, `tls.TlsFiles` writes it into a
directory made by `mkdtemp` (0700), each file created with `O_EXCL` and mode
0600, and removes the directory:

- once the context or client is built, where the driver reads the files once:
  `SSLContext.load_cert_chain` and pymongo, whose context is made in the
  client's constructor;
- when the pool closes, where the driver reads them at every connect:
  PostgreSQL's pool keeps its files and removes them in `close`; a connection
  made without a pool removes them once it is open; ZooKeeper's client keeps
  them until it is closed, the held one of a watch included.

Nothing is written for a block that names no PEM. A pool's key names the PEMs
by a digest (`TlsSettings.fingerprint`), never by where they were written, so
writing them again does not make a new pool. A test against `pg-tls` sees the
key file exist while the pool lives and gone with its directory after.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D448. The server's name through an SSH tunnel

A tunnel's end is a port on loopback; the certificate names the server.

- libpq dials `hostaddr` while `host` stays the form's, which is what it
  verifies.
- A context made by `tls.ssl_context(..., server_name=host)` substitutes the
  form's host in `wrap_socket` and `wrap_bio`, whatever the driver dialled: so
  MySQL, ClickHouse, Redis, RabbitMQ's AMQP and its management API (checked
  against the management address's host) verify the server through a tunnel.
  Cassandra names it through `ssl_options` as before.
- ClickHouse's and RabbitMQ's refusals of TLS through a tunnel are gone.
- pymongo and kazoo check the name they dialled and cannot be told another, so
  `verify_full` through a tunnel is refused there with a sentence naming
  `verify_ca`.

Known deviation:

- **Only the substitution is tested, not a tunnel to a TLS server.** The test
  stand has no TLS server behind the SSH server.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D449. An issued secret, asked for at every new connection

`app/adapters/cloud/` is driver-free. A source whose options name a cloud
account asks `AdapterContext.cloud` (`CloudAccess.issue(account, kind,
request)`) for an `IssuedSecret` — the value, when it expires, and a user name
when the issuer decides it — each time it opens a physical connection, and
keeps none.

- What is asked is a frozen `SecretRequest` subclass of the provider's (a host,
  a port, a user), so it is hashable.
- A provider is a `CredentialIssuer` registered for a kind: synchronous, as
  every cloud SDK is, and run in a thread by `connectors.cloud_accounts`. It
  words its own refusals as `AdapterError`s naming what to check; anything else
  it raises becomes "{kind} did not answer for the account {name}", with the
  SDK's exception neither chained nor logged beyond its type name (D184).
- `IssueCache` keeps what was issued in this process only, keyed by
  (account id, account version, request): reused until a minute before it
  expires, a secret that never expires by itself for five minutes, so a
  password rotated in its store is read again; concurrent asks for one key
  share one issue, a failure is never kept. Changing or deleting an account
  drops what it issued.
- `OwnerCloud` is always the owner's, built by `context_for` for every source —
  requests, the health monitor, the metrics collector, the search-keeper, the
  agent's tools, transfers, backups and pipelines all build their context
  there. It reads an account at most every 30 seconds, as `OwnerKeys` reads a
  key, and checks the account's kind and the ambient gate (D452) on every ask.

Known deviations:

- **Every kind's provider is installed** — AWS, Google, Azure and Vault. A
  kind without one would be kept and named, its test answering 501 and the
  form hiding Test, and a connection naming it would be refused at open with
  "This installation cannot sign in with accounts of {kind}".
- **Two contexts are built without it**: the source an SSH tunnel goes through
  (`connectors/tunnels.py`) and the readiness probe of a service started here
  (`services/readiness.py`). Neither signs in with a cloud account.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D450. A pool never keys on a token

A source asks its options' variant for `sign_in(cloud)` — user and password,
issued, read from a store or simply stored — at every physical connection,
and keeps none of it in the address a pool is kept by.

- PostgreSQL: `conninfo()` holds no password. The pool is keyed by
  `pool_identity`, the conninfo with every option, secrets by value, so an
  edited password still makes a new pool, and psycopg_pool's `kwargs` is the
  session's `credentials`, an async callable psycopg_pool resolves before
  every connection it opens.
- MySQL: aiomysql takes no callable, so the pool's connect arguments
  (`Pool._conn_kwargs`) are given the next user and password before every
  checkout; a connection opened during that checkout signs in with them.
- MongoDB: pymongo signs every connection of a client with what the client
  was made with, so the kept client is keyed by the issued keys; a role's
  keys, renewed hourly, make a new client and the old one goes when idle.
- Kafka and Redis open their clients per operation and sign in each time;
  S3's kept client holds refreshing credentials (D453).
- Programs (`psql`, `pg_dump`, the MySQL clients, `redis-cli`, `mongosh`,
  `mongodump`) and consoles ask when they start.

Proven against `pg-tls` with the IAM variant and a stand-in account: the
role's password is changed while a connection is open, a second connection
signs in with the new one, the pool is the same object, and the first
connection still answers. The same for MySQL's secret-store variant against
`mysql`. Neither is a real RDS: no AWS account is at hand.

Known deviation:

- **The MySQL pool's arguments are a private attribute** of aiomysql's pool,
  pinned by the test above rather than by aiomysql's documentation.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D451. Cloud accounts are the owner's, like SSH keys

Table `cloudaccount` (revision `e4b7c2a9f1d3`): owner (cascade), name unique
per owner, kind, method, the settings that may be shown as JSON, the secrets
as JSON encrypted under the connector key, and a version bumped on every change
of settings. Routes under `/cloud-accounts`: list (with the connections using
each), `schema`, create, change, delete, test.

- How an account signs in is declared like a connection's options
  (`adapters/cloud/accounts.py`): one discriminated union per kind on `method`,
  `SecretStr` marking what is encrypted (D4), so the connection form's
  `SchemaFields` draws it. `aws_access_key` (with an optional session token)
  and `aws_default_chain`, each with an optional role to assume (ARN, external
  ID, session name, length); `gcp_service_account` (the key file, checked to be
  a service account's) and `gcp_adc`, each with an optional service account to
  act as; `azure_service_principal` and `azure_default` (an optional
  user-assigned identity); `vault_token` and `vault_approle`, each with an
  address, a namespace and an optional CA.
- Secrets are write-only: the answer names which are stored, never their
  values, and an edit keeps a secret left empty when the method stays the
  same. An account keeps its kind (`cloud_accounts.kind_fixed`).
- A connection's field says `x-ui-purpose: cloud-account` and lists the kinds
  it takes in `x-ui-account-kind` (`cloud.account_field(*kinds)`): one, or all
  four for a secret store (D454). The account is checked to be the owner's and
  of one of them when the connection is saved — a 422 on the
  field — and again when it opens. A grantee's reads use the owner's account
  without seeing it (D33).
- An account a connection names is not deleted; the refusal names the
  connections, read off the schemas and stored options as a key's uses are.
- Preferences has a "Cloud accounts" section. The connection window's
  Parameters page has a "New account" button beside the SSH keys' in every
  connection, as keys do; where the form takes an account, it offers the
  owner's accounts of the field's kind, and the new account is of that kind and
  the field points at it.

Known deviation:

- **A connection handed to another owner keeps naming the old owner's
  account**, and is refused at open as one naming an account that is gone.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D452. The server's own identity is not a user's to borrow

`aws_default_chain`, `gcp_adc` and `azure_default` sign in as the machine
running DataPlayer — its environment, instance or container role, mounted
profile or managed identity. `CLOUD_AMBIENT_CREDENTIALS` (default `false`)
offers them:

- off, they are absent from the schema the form is built from and refused by
  the API (`cloud_accounts.ambient_off`), and an account made while it was on
  is refused when it opens;
- on, they are offered only to a superuser (`cloud_accounts.ambient_superuser`),
  and an account whose owner is no longer one is refused when it opens.

An address an account names follows the rule every outbound address already
follows: S3's endpoint and Vault's address go through one helper,
`adapters/addresses.http_origin` — an http or https origin and nothing else,
any host, a private one included, as a database's host or an SSH server may be.
The agent's outside MCP servers are the one place that refuses private
addresses (D360), because there the address is the agent's to follow.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D453. Cloud variants per source

Each is a variant of the source's flat union (D16), its fields declared by
`adapters/cloud/signin.py`'s factories where they belong, each answering
`sign_in`. AWS's provider is `adapters/cloud/aws/`, the one package besides
S3's that imports boto3.

| Source | Variant | What it does |
| --- | --- | --- |
| PostgreSQL, TimescaleDB | `aws_iam` | an RDS token for the form's host, port and user, signed locally; TLS not `disabled` |
| MySQL, MariaDB | `aws_iam` | the same token, sent by aiomysql's `mysql_clear_password` plugin, so only over Verify CA or Verify full; MySQL's own client is given `--enable-cleartext-plugin` |
| PostgreSQL, MySQL | `gcp_iam` | Cloud SQL's IAM sign-in with an access token (D455) |
| PostgreSQL, MySQL | `azure_entra` | a Microsoft Entra token for Azure's databases' scope; MySQL's with the cleartext plugin over verified TLS |
| Redis | `azure_entra` | Azure Cache for Redis: an Entra token for its scope, the principal's object ID as the user; TLS required |
| Redis | `aws_iam` | ElastiCache or MemoryDB: a signed `connect` for the cache's name and an IAM user; TLS required |
| MongoDB | `aws_iam` | `MONGODB-AWS` with the account's keys and session token, `$external`; needs `pymongo[aws]` |
| Kafka | `aws_msk_iam` | SASL/OAUTHBEARER with MSK's token; issued before a run, renewed by librdkafka's callback, which asks the event loop from its own thread and never from the loop's |
| S3 | `aws_account` | the account's keys as botocore's refreshing credentials, asked from the worker thread a request runs in a minute before they expire |

The token is signed for the host the form names, also through an SSH tunnel:
RDS and ElastiCache check the name they were signed for, which is the
server's. The cards "Amazon RDS for PostgreSQL" and "… for MySQL" start at
Verify full against Amazon RDS's authorities.

AWS's provider words every refusal from botocore's error code — a bad key,
expired credentials, denied, a role that cannot be assumed, a missing secret
or KMS key — never from its message. boto3 reads `AWS_ENDPOINT_URL` from the
environment; nothing a person types can point it elsewhere.

Azure's provider is `adapters/cloud/azure/`, the one package importing
azure-identity and msal: a service principal's secret, or this server's own
credential chain — environment, workload identity, managed identity (a
user-assigned one when named), the Azure CLI — gated as D452 says.

Known deviations:

- **S3 has one variant instead of four.** `session_token`, `assume_role` and
  `default_chain` are ways an AWS account signs in (D451), so S3 names an
  account rather than repeating them. Old S3 connections were given
  `auth_method = access_key` by `f2a9d4c7e1b3`, its statement tested
  against an old row.
- **Kafka's tools in a terminal refuse MSK IAM.** They need Amazon's plugin
  jar, which the image does not carry.
- **A 15-minute token can expire during a long dump.** The connection it
  opened stays valid; a program that reconnects would be refused.
- **What is proven where.** STS, an assumed role and Secrets Manager answer
  through moto in the test process, Microsoft Entra and Key Vault through
  `responses`, as azure-identity and msal speak HTTP to them; RDS, ElastiCache and MSK tokens are
  checked by their shape, signed here; S3 with an account's keys reads RustFS,
  Redis signs in to `redis-tls` with a token standing for its ACL user's
  password, PostgreSQL to `pg-tls` as above. No real RDS, ElastiCache, MSK,
  MongoDB Atlas or Azure database or cache was reached, and MySQL's cleartext sign-in has no server here.
- **DocumentDB does not take `MONGODB-AWS`;** the variant is for Atlas and
  servers that do.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D454. Secret stores and Vault's dynamic credentials

`secret_store` names an account of any of the four kinds, a secret, the JSON
key of the password (`password`) and of the user (`username`), and a user
that, left empty, is taken from the secret; PostgreSQL, MySQL and MongoDB
have it. It is read at every new connection, kept by the issued secrets'
cache for five minutes, so a password rotated in the store is followed
within minutes. A secret that is not JSON is the password whole.

AWS Secrets Manager and Google Secret Manager answer it now — Google's named
`projects/P/secrets/S[/versions/V]`, or by its name alone in the key file's
project, the latest version when none is named — and Azure Key Vault, named
`VAULT/NAME[/VERSION]` or by the identifier the portal shows. A Key Vault
token is sent only to Key Vault's own domains (`.vault.azure.net`, `.cn`,
`.usgovcloudapi.net`), never to an address somebody typed. Vault answers it
from a KV mount, version 1 or 2 as Vault says the mount is, named
`MOUNT/PATH`.

`vault_dynamic` (PostgreSQL and MySQL) names a Vault account, the database
secrets engine's mount (`database`) and a role. Vault makes a user and
password for the asking; its lease is their life, so the cache of issued
secrets hands the same pair to every new connection until a minute before
the lease ends, and then asks for a new one. The form has no user: Vault
names it with every lease, and the address shown names none.

Vault's provider (`adapters/cloud/vault/`) speaks Vault's HTTP API with
`requests`, so no client library is installed: a token, or an AppRole login
for one; a namespace when named; the account's CA, when given, written to a
private file for the call (D447). Its address follows D452's rule.

Known deviations:

- **Leases are not revoked.** Vault's credentials lapse with their lease; one
  made for a connection that closed early stays until then.
- **Proven against Vault's dev server** (`vault` in the `tools` profile and in
  CI): KV 1 and 2, AppRole, a token without the policy, and dynamic
  credentials whose role Vault made in the suite's own PostgreSQL, a
  connection signing in as it.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D455. Cloud SQL: its address, an IAM token and its server CA

Cloud SQL's IAM database sign-in is the `gcp_iam` variant of PostgreSQL and
MySQL: the password is an OAuth 2 access token for `sqlservice.login`, issued
by the account (a key file or this server's credentials, acting as another
service account when one is named) and good for an hour; the user is the IAM
principal as the instance names it — a service account's email without
`.gserviceaccount.com` for PostgreSQL, its name before the `@` for MySQL.
MySQL sends it with the cleartext plugin, so only over Verify CA or Verify
full; PostgreSQL refuses it without TLS.

The address is the instance's own (public or private IP, the instance's
server CA pasted on the TLS page, Verify CA, since the certificate names the
instance rather than its IP), an SSH tunnel to it, or a Cloud SQL Auth Proxy
run elsewhere, which is an ordinary host and port.

The Cloud SQL Python Connector was not taken. Its public API returns
connections of the drivers it supports — asyncpg async; pymysql, pg8000,
pytds and psycopg synchronous, psycopg through a local proxy thread — and
its per-driver adapters are internal; this application's PostgreSQL is async
psycopg with its own pool, and its MySQL is aiomysql. Taking its SSL context
would mean reaching into those internals.

Google's provider is `adapters/cloud/gcp/`, the one package importing
google-auth; Secret Manager is read over REST with the account's token, so no
gRPC client is installed.

Known deviations:

- **No ephemeral client certificate.** An instance that requires trusted
  client certificates takes one downloaded from the console in the TLS block;
  the Connector's per-hour certificate is not made here.
- **Proven only against mocked endpoints.** Google's token, impersonation
  and Secret Manager endpoints answer through `responses` in the test
  process, with a key file signing its assertion for real; no Cloud SQL
  instance was reached.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D456. Methods particular to one engine

- **Redis ACL users** (slice 1, D446): the password variant names a user,
  `default` when empty, signed in inside `HELLO`; `redis-cli` is given
  `--user`. Proven against `redis-tls`, whose default user is switched off.
- **Kafka mutual TLS**: no SASL, a client certificate and key in the TLS
  block, handed to librdkafka inline (D446).
- **Kafka OAUTHBEARER over OIDC** (`oauthbearer_oidc`): a token endpoint, a
  client ID and secret, an optional scope; librdkafka asks the endpoint for
  the token itself and renews it (`sasl.oauthbearer.method=oidc`).
- **MongoDB X.509** (`x509`): the TLS block's client certificate is who signs
  in, `MONGODB-X509` in `$external`, no password; the subject may be named or
  left to the server to read from the certificate. TLS and a certificate are
  required.

Known deviations:

- **Kafka's tools in a terminal refuse OIDC**, as they refuse MSK's IAM: the
  Java client's login handler for OIDC moved between Kafka's releases, and
  which one the image carries was not checked.
- **No Kerberos.** The confluent-kafka wheel in the backend image has no
  GSSAPI provider ("No provider for SASL mechanism GSSAPI", checked in the
  image). Its libpq does have GSSAPI, but Kerberos keeps its credential cache
  and client keytab per process, so every connection of every owner would
  share one identity; PostgreSQL's Kerberos is left out rather than offered
  shared.
- **Proven by what the drivers are handed** for OIDC and X.509: no OIDC
  provider and no MongoDB with client certificates run here.

Spec: [More ways to sign in to a connection](../../decisions/2026-11-22-connection-auth-design.md)

## D461. A region is chosen from what Amazon answers

Every field naming an AWS region — an AWS account's, the IAM variants' (D453)
and S3's — says so with `x-ui-purpose: aws-region`, and the form offers a
choice once `GET /cloud-accounts/regions` answers: the regions EC2's
`DescribeRegions` lists for the AWS account the form names, or, without one or
when it may not ask, the regions of Amazon's published IP ranges, read without
credentials and kept a day; botocore's own list when Amazon does not answer.
Titles ("Europe (Frankfurt)") are botocore's. The route never refuses: an
empty list leaves the box to type in. The empty choice comes first, and a held
region the list lacks stays a choice. S3's field carries
`x-ui-typed-when: endpoint`, so another provider's store keeps its typed
region. The account's own form asks the published list.

Spec: [AWS regions chosen, not typed](../../decisions/2026-11-27-aws-regions-design.md)
