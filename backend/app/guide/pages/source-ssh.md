# SSH

A server you reach over SSH. You browse its folders and work with its files as
with your own: tables, SQL over files, the editor, archives, search, copying
between connections, and a terminal. It signs in with a password or one of your
SSH keys, and only to the server whose key you confirmed. How connections work
in general is on the [Connections](connections.md) page.

## What you can see

- The server's folders and files, from where you choose
- Tables in CSV, TSV, Excel and Parquet files, and in logs
- Documents, code, images, PDFs, recordings and the insides of zip archives
- Files found by name, or by the text inside them
- SQL run over tables kept in files

## What you can change

- Files in a text editor
- The rows and columns of CSV and TSV files
- Files and folders: create, upload, rename, delete, download
- Archives: pack files into one, or unpack one
- Files copied or moved between folders and connections
- Anything else, from a terminal on the server

## Connecting

The **Connection** page of the window asks for:

- **Host** and **Port**, 22 unless the server says otherwise;
- **User**: the account to sign in as;
- **Folder**: where browsing starts. Empty is the account's home folder;
- **Server key**: what the server proves itself with (see below);
- **Authentication**: a password, or **Key**, one of your SSH keys.

A connection string such as `ssh://ann@files.example.com:22` pasted into **URL**
fills the host, port and user. A password is never part of it.

### The server key

Nothing is sent to a server until you have confirmed its key. This is what stops
a password or a key going to a machine that only pretends to be yours.

1. Fill in the host and port, then press **Fetch from the server**.
2. The server's fingerprint is shown. Compare it with the one the server's
   administrator gives you, or with what `ssh-keyscan` prints.
3. Press **Trust this key**.

A server that later presents a different key is refused, with a sentence saying
so. If the server was reinstalled, fetch its key again, compare, and press
**Trust the new key**. Only the connection's owner can do this.

A server started from **Start SSH server here** trusts the key it presented
first, because this application started it.

### SSH keys

Your SSH keys are on the **Preferences** page, apart from connections, so one key
serves as many connections as you point at it.

- **New key** makes a key on this server: ED25519, or RSA for servers that
  refuse ED25519. **Import** takes a private key you paste or choose as a file.
- **Copy the public key** copies the line to add to `~/.ssh/authorized_keys` on
  the server. It ends in `dataplayer`, so the server's owner can tell which line
  it is.
- The private half of a key is never shown again, to anybody.
- A key can have a passphrase, kept one of three ways: none; stored beside the
  key; or asked for when the key is needed and held for 15 minutes, an hour or
  eight hours. **Lock it now** forgets it early.
- A key that is locked stops its connections. Every screen that reads the
  connection then offers **Unlock the key** in place of an error.
- A key used by a connection cannot be deleted. Point the connection at another
  key first.

## The catalog and the files

An SSH connection is browsed exactly like a [Files](source-file.md) connection:
the same catalog, the same search by name and inside files, the same viewers,
the same editor, the same actions (**New folder**, **New file**,
**Upload files**, **Rename**, **Delete**, **Download**, **Archive**, **Extract**,
**Copy**, **Cut**, **Paste**), and the same SQL over files.

Nothing runs a command on the server for these: everything goes through SFTP.

Differences from your own files:

- **Connect folder** is not offered.
- A file larger than 200 MB is not opened as a table, a workbook, an archive or
  in SQL: download it instead. Text, pictures, PDFs and recordings open whatever
  their size.
- A search inside files skips files over 1 MB and stops after 32 MB in total,
  because every byte crosses the network.

## The terminal

**Terminals**, on the left rail, opens a terminal in the panel at the foot of
the screen: the login shell of the connection's account, on the server.

- Only the connection's owner can open one. People the connection is shared
  with cannot.
- The shell starts in the account's home folder, not in the connection's
  **Folder**.
- Closing the terminal, closing the page or losing the network ends the shell.
  It is not reattached; open another.
- Several terminals can be open at once, up to eight. Switching to another tool
  in the panel keeps them running.
