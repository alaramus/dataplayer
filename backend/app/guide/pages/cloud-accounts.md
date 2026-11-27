# Cloud accounts

A cloud account is how a connection reaches a cloud on your behalf: to get a
token that signs in to a database, or to read a password kept in a secret
store. It is yours, as an SSH key is: a connection names it, and somebody you
share the connection with uses it without seeing it. Accounts are kept in
**Preferences**, under **Cloud accounts**; the **Options** page of a
connection window has a **New account** button too.

## Kinds

- **Amazon Web Services**: an **Access key** and its **Secret key**, with a
  **Session token** for temporary credentials. It can assume a **Role** — its
  ARN, an **External ID**, a session name and length.
- **Google Cloud**: a **Service account key** file, as JSON. It can act as
  another service account, which then needs to let it.
- **Microsoft Azure**: a **Service principal** — tenant, client ID and client
  secret.
- **HashiCorp Vault**: its **Address**, a namespace and a CA certificate when
  needed, and a **Token** or an **AppRole** role ID and secret ID.

Secrets are kept encrypted and never shown again. **Test** makes the cheapest
harmless call the account allows and says who signed in.

## This server's own identity

An account can also sign in as the machine DataPlayer runs on: AWS's default
credential chain, Google's Application Default Credentials, an Azure managed
identity. Anybody could borrow that identity, so it is offered only where the
installation allows it, and then only to a superuser.

## What a connection does with one

A token is issued for every new connection and kept only in memory until
shortly before it expires; nothing issued is stored. Each source's page says
which of its ways of signing in take an account:

- PostgreSQL and MySQL: AWS IAM (RDS), Google Cloud IAM (Cloud SQL), Microsoft
  Entra, a secret store, Vault's dynamic credentials.
- Redis: AWS IAM (ElastiCache, MemoryDB), Microsoft Entra.
- MongoDB: AWS IAM (MONGODB-AWS), a secret store.
- Kafka: AWS IAM (MSK).
- S3: an AWS account instead of a key.

A **Secret store** names the secret where it is kept: on AWS by its name or
ARN; on Google as `projects/P/secrets/S`, or by its name alone in the key
file's project; on Azure as `VAULT/NAME`; on Vault as `MOUNT/PATH`. A secret
that is JSON is read by its `password` and `username` keys, which can be
renamed; any other secret is the password itself.

A server that checks passwords against LDAP, PAM, RADIUS or Active Directory
needs no account: to DataPlayer it looks like a password.

## Limits

- An account keeps its kind; make a new one for another cloud.
- An account a connection uses cannot be deleted; the refusal names the
  connections.
- A token that expires during a long backup does not stop it: the connection
  it opened stays valid.
- Kafka's tools in a terminal cannot sign in with AWS IAM or OIDC yet.
