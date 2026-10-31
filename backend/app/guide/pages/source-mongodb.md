# MongoDB

A MongoDB server. You browse its databases and collections and read documents
a page at a time as rows, with the fields of a collection found from its
documents. How connections work in general is on the
[Connections](connections.md) page.

## What you can see

- Databases, collections, views and time series
- Documents as rows, sorted and filtered on the server
- The fields a collection's documents have, and its indexes
- A collection's definition: its options, validator and indexes, as JSON
- Every document whole, as JSON, a page at a time
- How many documents a collection holds and how much space it takes
- mongosh, signed in as the connection, in a terminal
- Every matching document, downloaded as a file
- The server's operations, connections, users and roles
- The server's counters, on a dashboard

## What you can change

- Documents: edit fields, paste blocks, add and delete documents
- A field in every document: add, drop, rename, convert to another type
- Indexes: ascending, descending, hashed, text and geospatial; unique or not
- Databases and collections: create, rename, move, drop; load a CSV
- A running operation: stop it from its report
- Collections copied into another MongoDB connection with their indexes
- The connection's database: backed up to a file and restored from one
- Anything mongosh can change, typed into its terminal

## Connecting

The **Connection** page of the window asks for:

- **Host** and **Port** of one server, 27017 unless it listens elsewhere;
- **TLS**: an encrypted connection, with the server's certificate checked;
- **Authentication**: a user and a password, or none for a server started
  without access control. The **Authentication database** is where the user
  was made, `admin` unless it was made in another;
- **Database**: where the catalog opens. It may be left empty. Every database
  the user may see is in the catalog either way.

A connection string such as `mongodb://ann@db.example.com:27017/shop` pasted
into **URL** fills these fields; `?authSource=` and `?tls=true` are read too.
A password in the pasted string goes into the password field and leaves the
string.

The server named is the server spoken to. A member of a replica set is read
as it is; to change data, name the primary. A `mongodb+srv://` address and a
list of servers are not supported.

MongoDB 5.0 and later is supported. An older server is refused when the
connection is checked, with its version named.

## The catalog

- The first level is databases. The one the connection names comes first,
  even before anything is stored in it; `admin`, `local` and `config` belong
  to the server and are marked as such.
- Inside a database are its collections and views. A collection says how many
  documents it holds and how much space it takes on disk.

## Documents as rows

- The columns of a collection are the fields of its documents: those its
  validator declares, then those found in the first and the last hundred
  documents. `_id` comes first. A field met only in a document outside those
  is shown on the page that holds it, and cannot be sorted or filtered by.
- Each column says the type its documents hold: a string, a number, a date, an
  ObjectId, an object, an array. A field whose documents disagree is mixed.
- An ObjectId is shown as its hex, a date in UTC with a `Z`, a decimal with
  all its digits. An object or an array is shown as JSON, in the form
  `mongosh` writes; so is any value with no plain spelling.
- A missing field and a field holding null both show an empty cell, and both
  match **is empty**.
- A filter value is read as the field holds it: a number as a number, a date
  as a moment, an ObjectId as its hex. Text that looks like a query is only
  text.
- A page with no sort of your own is ordered by `_id`, so the next page never
  repeats the last one.
- A field whose name holds a dot or starts with `$` is shown but cannot be
  sorted or filtered by: a query cannot name it.

## Changing documents

- A cell is one field of one document. What you type is stored as the field
  holds values: a number as a number, a date as a moment, an object or an
  array as JSON in the form the cell shows. A field of mixed type takes JSON
  when what you type is JSON, and text when it is not.
- A document changed by somebody else since the page was read is not
  overwritten: you are told, and the page is read again.
- `_id` cannot be changed. Emptying a cell stores null.
- A new document holds the fields you fill in and no others; leave `_id`
  empty and one is made.
- A pasted block is checked whole first, then written a document at a time.
  A block of new documents goes in whole or not at all.
- A view, a time series and the server's own collections are not changed
  here; a time series takes new documents.
- **View as documents** shows every document whole, every level of it.

## Structure

A collection's columns are its documents' fields, so the structure screen
changes every document at once:

- **Add** sets the new field to null in every document that lacks it.
- **Drop** removes the field from every document; **rename** renames it in
  each.
- **Change type** converts every value with the server's own conversion. If
  any value would not convert, you are told how many and nothing changes.
  Empty values stay empty.
- A unique index is not made when documents repeat its values; you are told
  how many values repeat.
- A view, a time series and the server's own collections keep their
  structure. A validator is changed in mongosh.

## The catalog's actions and the Server section

- **New database** asks for the name of its first collection too: MongoDB
  keeps a database only while it holds something.
- A collection is renamed, moved to another database with its documents and
  indexes, or dropped. A view can only be dropped.
- Dropping says first which views read what goes, and how many documents it
  holds. A database that still holds anything is dropped only when you ask
  for everything in it to go.
- **Load from CSV** makes a collection of the file's rows; every value is
  text, and an empty one is no field.
- The **Server** section after the databases holds Operations, Connections,
  Users and Roles. **Stop operation** stops what you picked in Operations.
- Search finds databases, collections and reports by name, not by field.

## Copies, backups and a server of your own

- **Copy tables** copies collections into a database of another MongoDB
  connection, or of this one: their options and validator, every document as
  it is stored, and their indexes. Views and time series are not copied.
- A backup is `mongodump`'s archive of the database the connection names; a
  restore writes it back over that database with `mongorestore`, replacing the
  collections it holds. It is not offered through an SSH tunnel.
- **Services** can start a MongoDB of your own, with a password nobody has to
  choose, and fill it with the lab: a `demo_lab` database of customers,
  products, orders, page views as a time series and a view.
- A dashboard made from the **MongoDB server** layout draws connections,
  operations, documents, memory, network and size.

## mongosh

**Open a terminal** on a MongoDB connection of your own starts `mongosh`,
signed in as the connection and in its database, in the terminal panel. It is
the real shell, with all its commands; what it prints stays on its screen.

- It runs in a container this server starts for it, so it opens only
  where the server may start containers. The first one waits while the image
  is fetched.
- It reaches the database as a backup does, by the host the connection names;
  not through an SSH tunnel.
- Closing the terminal ends the shell. `exit` ends it too.
