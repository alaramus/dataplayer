# Signing in to a connection: TLS, client certificates, issued secrets

For changing how a server source encrypts its connection, which certificate it
trusts or offers, a person's cloud accounts, and how a password is issued by a
cloud or fetched from a secret store for every new connection.

Decisions here: D446, D447, D448, D449, D451, D452.

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

- **No provider is installed yet.** The issuers arrive with their slices; until
  then an account can be kept and named, its test answers 501 and the form
  hides Test, and a connection naming it is refused at open with "This
  installation cannot sign in with accounts of {kind}".
- **Two contexts are built without it**: the source an SSH tunnel goes through
  (`connectors/tunnels.py`) and the readiness probe of a service started here
  (`services/readiness.py`). Neither signs in with a cloud account.

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
- A connection's field says `x-ui-purpose: cloud-account` and
  `x-ui-account-kind` (`cloud.account_field(kind)`). The account is checked to
  be the owner's and of that kind when the connection is saved — a 422 on the
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
