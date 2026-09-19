# An SSH source, its server key and its keys

Date: 2026-09-19. Decisions: D144, D145, D146, D147.

Status: implemented with this specification. The terminal is the next slice
and is not decided here.

## What was asked

A source type for SSH servers, as the old application had, and a terminal that
works differently per source — a shell on the remote server for SSH. The
terminal for personal storage was postponed; SSH comes first. Before anything
was written the owner asked for the question of private keys to be settled
properly: the old application had thought about it at length, and a private
key is the credential with the widest reach this application would hold.

## The old application

- The catalog ran `ls -la` over an exec channel and parsed the output; file
  operations used SFTP.
- Keys were uploaded by name into an encrypted per-user store; a passphrase
  could be saved for a limited time and deleted afterwards.
- The terminal ran a local `ssh` process in a pty, with the key written to a
  temporary file, an askpass script for the password and an `ssh-agent` per
  user.
- Host keys were not verified: `known_hosts=None` in the library, and
  `ssh-keyscan` plus `StrictHostKeyChecking=accept-new` for the terminal.

## How others do it

Researched before deciding, so that nothing here is invented where a practice
exists:

- **Server keys.** Jenkins offers three strategies — a `known_hosts` file,
  accept the first connection, or keys entered by hand — and turned
  verification on by default after an advisory in 2022. Bitbucket Pipelines
  fetches a host's fingerprint, shows it and asks to add the host. Apache
  Guacamole keeps a `host-key` per connection.
- **Where private keys live.** AWX, Semaphore and CloudBeaver keep them
  encrypted under a key in the configuration; CloudBeaver states plainly that
  access to the server's files gives access to every stored credential.
  Rundeck's key storage lets a private key be written and never read back.
  Coolify generates ED25519 keys itself and shows the public half to add to
  `authorized_keys`, as GitHub deploy keys scope one key to one purpose.
- **Passphrases.** AWX stores one or prompts on launch; Guacamole prompts when
  none is stored; `ssh-add -t` gives an agent a lifetime.
- **Beyond keys.** Termius encrypts end to end under a master password, which
  works because its client signs in, not its server. Vault's SSH engine and
  Teleport replace keys with short-lived certificates, which needs every
  target server to trust a CA. OWASP recommends keeping the key-encryption key
  in another system.

## Decisions

- **D144.** SFTP only, no command on the server; the catalog stands in the
  connection's folder or the home folder; the five file actions on the file
  source's forms; a kept connection per stored connector; the library's
  defaults that reach outside the connection refused.
- **D145.** The server's key is fetched and its fingerprint shown before any
  credential is sent, pinned in the connection, required on every connection
  after, and re-trusted only by the owner. No "do not verify" mode.
- **D146.** A person's key store, separate from connections: generate (ED25519
  by default) or import; the private half write-only and encrypted under the
  connector key; connections name a key by id and receive it when signing in;
  a key in use is not deleted.
- **D147.** A passphrase is stored or asked for; an asked one is held in the
  process for 15 minutes, 1 hour or 8 hours, checked when given, asked on
  every use, and forgotten on restart. A locked key is the error kind
  `locked`.

## Not decided here

- The terminal: a per-source capability in the panel at the foot of the
  workspace (D143), SSH first.
- An SSH tunnel for other sources, which the old application had.
- Short-lived certificates, and a KMS or Vault for the connector key.
- Search, summaries and tabular reading over SFTP; downloading a folder.

## Tests

- `tests/adapters/test_ssh_keys.py`: making, importing and describing keys;
  refusals that never quote a key; nothing secret in a `repr`.
- `tests/adapters/test_ssh.py`: registration, capabilities, the schema's
  secrets and key references, no connection without a pinned key, the path
  rule.
- `tests/adapters/test_ssh_server.py`: against `sshd` — a pinned key checks, any
  other is refused before signing in, a wrong password, the catalog, reading,
  downloading, uploading with each conflict rule, renaming and deleting,
  editing a file only while it is the version read with its permissions kept,
  and a key that signs in and then stops a kept connection when it is locked.
- `tests/connectors/test_ssh_key_routes.py`: the store through the API — no
  private half in any answer or in plain text at rest, import only with the
  passphrase that opens a key, unlock and lock, a key in use not deleted,
  another owner's key not answering.
- `tests/connectors/test_keyring.py`: a passphrase forgotten on time and on
  locking.
- `tests/connectors/test_server_key_routes.py`: 501 for a source that pins
  nothing, describing without a network call, and comparing against the
  server.
- `frontend/src/features/sshKeys/keys.spec.ts`: the words for a key's state,
  the spans offered, and the form's choice of keys.
- `frontend/src/shared/api/retry.spec.ts`: a `locked`, `auth` or `config`
  answer is not asked again.
- `frontend/tests/ssh.spec.ts`: a key made on the Preferences page shows no
  private half; an SSH connection refuses to check before its server key is
  trusted, is trusted from what the server presents, and is browsed.
