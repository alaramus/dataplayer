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
- How many documents a collection holds and how much space it takes
- mongosh, signed in as the connection, in a terminal

## What you can change

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
