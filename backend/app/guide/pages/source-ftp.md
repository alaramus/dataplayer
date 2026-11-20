# FTP

A server reached over FTP or FTPS. You browse its folders from where you choose
and work with its files as with your own: tables, SQL over files, the viewers
and search. It signs in with a password or anonymously. How connections work
in general is on the [Connections](connections.md) page.

## What you can see

- Folders and files below the folder you choose
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

## Connecting

The **Connection** page of the window asks for:

- **Host** and **Port**: 21, or 990 for implicit TLS;
- **Encryption**: **TLS, explicit** is what most servers speak today, on port
  21. **TLS, implicit** is the older FTPS on port 990. **No encryption** sends
  the password as you type it: choose it only for a server that offers nothing
  else;
- **Verify the certificate**: switch it off only for a server whose
  certificate you made yourself;
- **Folder**: where browsing starts. Empty is the folder the server signs you
  into, `/` is the top of the server;
- **Authentication**: a **User** and **Password**, or **Anonymous** for a
  public server.

**URL** shows the server as `ftp://user@host/folder`, and `ftps://` for
implicit TLS. An address pasted into it fills the host, the port, the user and
the folder. The password is never part of it.

## The catalog and the files

An FTP connection is browsed like a [Files](source-file.md) connection: the same
catalog, the same search by name and inside files, the same viewers and the same
SQL over files. The same actions too: **New folder**, **New file**, **Upload files**,
**Rename**, **Delete**, **Download**, **Archive**, **Extract**, **Copy**, **Cut**
and **Paste**.

How a server over FTP differs from a disk:

- The server's own permissions decide what you may read and change.
- A file whose name is not in UTF-8 is not shown. It is still on the server.
- Some servers list times only to the minute, or only the day for older files,
  and none says its time zone: times are shown as UTC.
- A file larger than 200 MB is not opened as a table, a workbook, an archive
  or in SQL: download it instead. Text, pictures, PDFs and recordings open
  whatever their size.
- A search inside files skips those over 1 MB and stops after 32 MB in total,
  because every byte crosses the network.
- Copying passes every byte through DataPlayer, because FTP has no copy of its
  own: up to 200 MB at once.
- A file saved over one that changed meanwhile is refused rather than
  overwritten.
