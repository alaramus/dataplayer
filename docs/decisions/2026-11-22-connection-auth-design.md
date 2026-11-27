# More ways to sign in to a connection

Decisions D446–D456. A connection signed in with a user and a password or with
nothing, and TLS was a different switch, or none, in every source. Managed and
production servers want more: TLS that verifies what it should and offers a
client certificate, a password that is a short-lived token issued by a cloud
for every new connection (RDS IAM was the case that started this), a password
kept in a secret store, and a few methods particular to one engine.

## Facts checked before the design

Versions are those in `uv.lock` on 2026-11-22 (Python 3.14).

| Driver | What it takes for TLS (checked in the installed code) |
| --- | --- |
| psycopg 3.3.9 / libpq | `sslmode`, and `sslrootcert`, `sslcert`, `sslkey` as **file paths** read at every connect; `hostaddr` dials an address while `host` stays the name verified. `sslpassword` for an encrypted key |
| aiomysql 0.3.2 / PyMySQL 1.2.4 | `ssl=` an `SSLContext`; the server name it verifies is the host it dials |
| redis-py 8.1.0 | `SSLConnection` builds its own context from `ssl_*` arguments, cert and key as files; any `Connection` subclass may put an `SSLContext` of its own into `_connection_arguments()` |
| pymongo 4.20.0 | `tls`, `tlsCAFile`, `tlsCertificateKeyFile`, `tlsCertificateKeyFilePassword`, `tlsAllowInvalidCertificates`, `tlsAllowInvalidHostnames`; the context is built once, when the client is constructed |
| scylla-driver 3.29.13 | `ssl_context` and `ssl_options={"server_hostname": …}` |
| kazoo 2.11.0 | `use_ssl`, `ca`, `certfile`, `keyfile`, `keyfile_password` as files, `verify_certs`, `check_hostname` (default **False**), read at every connect, so also at every reconnection |
| confluent-kafka 2.16.1 | `ssl.ca.pem`, `ssl.certificate.pem`, `ssl.key.pem`, `ssl.key.password` inline; `ssl.endpoint.identification.algorithm` `https` by default |
| aio-pika 10.2.3, httpx 0.28.1 | an `SSLContext` |

So: what takes an `SSLContext` gets one; libpq and kazoo need files that live as
long as a connection may be opened; pymongo needs files only while the client
is constructed.

## D446. One TLS block, every server source

A module without drivers, `app/adapters/tls.py`, declares the fields once and
each source puts them on its base model:

- `tls_mode`: `disabled`, `preferred` (only where the driver can fall back:
  PostgreSQL and MySQL), `required` (encrypted, nothing verified), `verify_ca`
  (the chain, not the name), `verify_full` (chain and name).
- `tls_trust`: where the chain ends — `system` (the system's authorities),
  `certificate` (the PEM in `tls_ca_certificate`), `amazon_rds` (a bundle of
  Amazon RDS's authorities shipped with the application, offered where RDS or
  DocumentDB can be on the other end: PostgreSQL, MySQL, MongoDB).
- `tls_ca_certificate`, `tls_client_certificate`: PEM, not secret.
- `tls_client_key`, `tls_client_key_passphrase`: `SecretStr`.

The fields are flat (D16) and sit on a page of the connection window of their
own, "TLS", through `layout(group="tls")`: the form keeps declaration order,
and a block put on the base model would otherwise land between the address and
the choice of method.

A helper turns the block into an `ssl.SSLContext` (Docker's `tls_context`,
D418, is the second use and moves there) and exposes the PEMs, normalised the
way Docker's form already normalises them, for drivers that take them inline.

**Existing rows behave exactly as before.** PostgreSQL's and MySQL's default
is `preferred`, which is what libpq's `prefer` and MySQL's current context do.
The sources with a switch lose it to `tls_mode` through one data migration,
statement named, tested against an old row:

| Source | Old field | `true` becomes | Why |
| --- | --- | --- | --- |
| MongoDB | `tls` | `verify_full` | pymongo verifies the name by default |
| ClickHouse | `secure` | `verify_full` | httpx `verify=True` |
| Cassandra | `secure` | `verify_full` | `create_default_context` with `server_hostname` |
| ZooKeeper | `tls` | `verify_ca` | kazoo's `check_hostname` defaults to False |
| Kafka | `tls`, `ca_certificate` | `verify_full` | librdkafka's `https` identification |
| RabbitMQ | `tls`, `ca_certificate` | `verify_full` | `create_default_context` |

`false` becomes `disabled`; a non-empty `ca_certificate` becomes
`tls_trust = certificate` with the PEM moved to `tls_ca_certificate`. Keeping
the old switch beside the new fields was rejected: two fields meaning one
thing, one of them able to contradict the other.

Redis gets TLS, and the refusal of `rediss://` (D15's deviation) goes: a
`rediss://` address is read as `verify_full`.

## D447. Key material on disk is private and short-lived

What the standard library and libpq read only from files is written to a
directory made by `tempfile.mkdtemp` (mode 0700), each file created with
`O_EXCL` and mode 0600, and removed:

- right after the context or client is built, where the driver reads the
  files once (`SSLContext.load_cert_chain`, pymongo);
- when the pool closes, where the driver reads them at every connect
  (PostgreSQL's pool, ZooKeeper's held client); a connection made without a
  pool removes them once it is open.

The directory is per pool, never shared between connectors, and nothing is
written when the block names no client key and no CA.

## D448. Verifying the name through an SSH tunnel

A tunnel's end is a port on loopback, and the certificate names the server.
Where the driver lets the name be stated, it is the form's host: libpq through
`hostaddr`, Cassandra through `server_hostname`, and every driver that takes an
`SSLContext` through a context whose `wrap_bio`/`wrap_socket` substitute the
form's host for the one dialled. Where it cannot (pymongo, kazoo),
`verify_full` through a tunnel is refused with a sentence naming `verify_ca`;
ClickHouse's blanket refusal of HTTPS through a tunnel is lifted.

## D449. An issued secret, asked for at every new connection

`app/adapters/cloud/` holds a protocol, `CredentialIssuer`, returning an
`IssuedSecret` (value, expiry, optional user). A driver asks for one each time
it opens a physical connection and keeps none. A process-local cache keyed by
(account id, account version, what is asked) reuses a value until a minute
before it expires and coalesces concurrent issues; nothing issued reaches the
database, Redis, a log or an answer. SDKs are synchronous and called in a
thread; every failure becomes an `AdapterError` with a sentence saying what to
check (denied, expired credentials, region, role), never SDK text.

`AdapterContext.cloud` (`CloudAccess`) is always the owner's accounts, built
by `connectors/` wherever an `AdapterContext` is built: requests, the health
monitor, the metrics collector, the search-keeper and the agent's tools.

Programs (backups, terminals) and second connections (roles, users) are handed
a fresh secret when they start. A token that expires during a long `pg_dump`
is a known deviation, not hidden: the connection it opened stays valid.

## D450. A pool never keys on a token

The pool key is the stable options, the account id and the account's version.
A pool creates every physical connection with a freshly issued secret:
psycopg_pool's `kwargs` are fixed at construction, so the pool's
`connection_class` overrides `connect` to ask for the secret; aiomysql's pool
is given a connect function the same way. A fake issuer proves that two new
connections after expiry carry different tokens, the pool is the same object,
and a connection already open keeps working.

## D451. Cloud accounts are the owner's, like SSH keys

A table `cloudaccount` (owner, name unique per owner, kind, public settings as
JSON, secrets encrypted under the connector key, a version bumped on every
change), routes under `/cloud-accounts`, write-only secrets. Kinds: `aws`
(static key with optional session token; assume role over a static key or the
default chain; default chain), `gcp` (service-account JSON; Application Default
Credentials; optional impersonation), `azure` (service principal; default
credential), `vault` (address, namespace, token or AppRole, optional CA). Test
makes the cheapest harmless call. An account a connection names cannot be
deleted, and the refusal names the connections. A grantee uses the owner's
account without seeing it (D33). A connection field says
`purpose = "cloud-account"` and the kind it accepts; the kind is checked when
the connection is saved and again when it opens.

## D452. The server's own identity is not a user's to borrow

Default credential chains, ADC and managed identity are the identity of the
machine running DataPlayer. `CLOUD_AMBIENT_CREDENTIALS` (default off) offers
them; when off they are absent from the form and refused by the API, and when
on only a superuser may make such an account. An address an account names
(Vault, a custom endpoint) follows the policy outbound addresses already
follow (checked in slice 2 against S3's endpoint and SSH hosts).

## D453. Cloud variants per source

| Source | Variants |
| --- | --- |
| PostgreSQL, TimescaleDB | `aws_iam`, `gcp_iam`, `azure_entra`, `secret_store`, `vault_dynamic` |
| MySQL, MariaDB | the same; the cleartext plugin over TLS (checked in slice 3) |
| Redis | `password` gains an ACL user; `aws_iam` (ElastiCache, MemoryDB), `azure_entra` |
| MongoDB | `x509`, `aws_iam` (`MONGODB-AWS`), `secret_store` |
| Kafka | `oauthbearer_oidc`, `aws_msk_iam`, mTLS through D446 |
| S3 | `access_key` (today's) and `aws_account`: a session token, a role and the default chain are an account's ways of signing in (D451), so S3 names an account instead of four variants (changed in slice 3) |
| ClickHouse, RabbitMQ, Cassandra | D446; certificate sign-in where the client makes it simple |

LDAP, PAM, RADIUS and Active Directory simple bind look like a password to the
client; the guide says so instead of growing empty variants.

## D454. Secret stores and Vault's dynamic credentials

`secret_store` names an account (AWS Secrets Manager, Google Secret Manager,
Azure Key Vault or Vault KV by kind), a secret and the JSON key of the
password (and of the user, or the user typed). `vault_dynamic` names a Vault
account, a database secrets mount and a role; the lease is the expiry.

## D455. Cloud SQL

Decided in slice 4: the Cloud SQL connector's connection-info API if it gives
an `SSLContext` and an address cleanly, otherwise direct IP with the IAM token
and the instance's server CA, the official proxy remaining an ordinary host
and port.

## D456. Engine-native methods

Redis ACL users, MongoDB X.509, Kafka OAUTHBEARER over OIDC and mTLS. Kerberos
only where the shipped wheels support it, otherwise a known deviation.

## Plan

One commit per slice on `connection-auth`, each stopping for review.

0. This spec.
1. D446–D448: `adapters/tls.py`, the block on PostgreSQL/Timescale, MySQL,
   ClickHouse, Redis, MongoDB, Cassandra, Kafka, RabbitMQ, ZooKeeper; the data
   migration; consoles and backups following the mode; the RDS bundle; Docker
   on the shared helper; test servers for PostgreSQL with client certificates
   and Redis with TLS and an ACL user.
2. D449, D451, D452: accounts, migration, routes, ambient gate, issuer and
   cache, `AdapterContext.cloud` everywhere, Preferences, the form's purpose.
3. AWS: RDS IAM for PostgreSQL, MySQL, MariaDB with D450's proof; Secrets
   Manager; ElastiCache; S3 roles; MSK; MongoDB-AWS. moto in the test process
   for STS and Secrets Manager rather than LocalStack in the `tools` profile:
   nothing to start, and the provider's calls are checked where they run;
   S3 is proven against RustFS (changed in slice 3).
4. Google: D455, Secret Manager.
5. Azure: Entra for PostgreSQL, MySQL, Redis; Key Vault.
6. Vault (a dev server in `tools`): static and dynamic; Kafka OIDC and mTLS;
   MongoDB X.509; Redis ACL users.
7. Guides, translations everywhere, the full checks.

What cannot be proven here: RDS, Cloud SQL and Entra token sign-in are proven
only against a fake issuer, since no cloud account is available.
