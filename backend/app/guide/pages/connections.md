# Connections

A connection is a saved way to reach one source: a PostgreSQL database, a Redis
server, a folder of your own files or a server over SSH. Catalogs, tables,
query consoles, pipelines and dashboards all work through connections.

Each kind of source has a page of its own: [Files](source-file.md),
[PostgreSQL](source-postgres.md), [Redis](source-redis.md) and
[SSH](source-ssh.md).

## The list of connections

The **Connections** column is on the left of the **Data** space. The
**Pipelines** space shows the same list.

- Press a connection's name to open its catalog. It opens in the column beside
  the list, as a tab named after the connection.
- Press a connection's icon to open its window, where it is edited.
- **+** at the head of the column adds a connection.
- The magnifier turns the head into a filter by name. **Esc** or the cross
  closes it.
- The arrow at the end of the head reads the list again.
- The button at the top left of the screen narrows the column to icons and
  widens it again. The narrow column still opens catalogs and still has **+**.

A dot on each icon says what the last check found:

- green: the source answered;
- red: the source did not answer, or refused;
- yellow: the connection is switched off;
- grey: it has not been checked yet.

Connections are checked while the workspace is open. How often is set on the
**Preferences** page.

## Adding a connection

1. Press **+** at the head of **Connections**. The **New connection** window
   opens.
2. Pick a kind of source. The kinds are grouped on the left: **SQL Databases**,
   **Key-Value Stores**, **Files & Storage**. The search box finds a kind by its
   name or by what it can do.
3. The panel on the right says what the kind is, what you can see and change
   through it, and has **Guide**, which opens its page of this guide.
4. Press **Create connection**, or double-click the kind. The connection
   window opens for it.
5. Fill in the fields, press **Test Connection**, then **OK** to save and close,
   or **Apply** to save and keep the window open. **Back** returns to the list of
   kinds without saving.

Where this server can run containers, the panel also offers to start a new
server of that kind on this machine: **Start PostgreSQL here**,
**Start TimescaleDB here**, **Start Redis here** or **Start SSH server here**.
The window that opens asks **How**:

- automatically: the server is named for you, gets a password nobody has to
  choose and comes filled with sample data, so there is something to look at;
- with your own choices: a name, a user, a database, a port on this machine,
  and for an SSH server whether you sign in with a password or one of your SSH
  keys.

Either way the connection is made for you. How the start is going is shown in
the activity bell at the bottom right. When the server is ready, a window shows
where to reach it from your own tools and its password, once. Copy the
password then if you need it elsewhere.

A button that is greyed out says why when you point at it: this installation
may not run containers at all.

## The connection window

The window of a connection opens when you add one or press its icon. Several
can be open at once, so you can read one connection while filling in another.
Closing a window with changes that were not saved asks first.

- **Name** is how the connection is listed. It is required.
- **Tab color** colours the connection's tabs and its row in the list.
- **In use** switches the connection off without deleting it. A switched-off
  connection keeps its settings, cannot be opened and has a yellow dot.
- **URL** is the connection string composed from the fields. The password is
  never part of it. Paste a connection string into it and the fields are filled
  from it. The copy button next to it copies the string.
- **Test Connection** tries to connect with what the form holds now, saved or
  not. The answer appears in a small popup above the button.
- **Delete** removes the connection. Only its owner has it, and it asks first.

The window has three pages at least.

### Connection

How to reach the source. The fields depend on the kind of source and are
described on its page. A choice of **Authentication** changes which fields are
shown.

### Options

**Keep answers** says how long a catalog level and a page of rows may be
reused before the source is read again.

- **As this source decides** is the default. The label says how long that is.
- **Never keep answers** reads the source every time.
- **Keep for …** sets a time of your own, up to a day.

Pressing a reload button always reads the source, whatever is chosen here. A
small mark beside the reload button says **Live** while the answer on screen is
fresh from the source, and shows a clock once it is one that was kept. Hover it
to see how old it is.

A source that keeps nothing says so, and the field is switched off.

### Permissions

- **Consoles** decides what a query console may do on this
  connection: **Read only**, **Ask before writing** (the default) or
  **Writing allowed**. It applies to everybody the connection is shared with.
- **Allow sending data to third parties** decides whether data read through
  this connection may be sent to an outside service, such as an AI model
  provider. It is off unless you switch it on.
- **Who else may reach it** lists the people the connection is shared with and
  the requests waiting for an answer. **Share** gives it to somebody.

## Sharing a connection

A connection belongs to the person who made it. The owner can give other
people one of three levels:

- **Read**: open the catalog, read rows, download and chart them;
- **Edit rows**: also change, add and delete rows;
- **Change structure**: also change columns, indexes, keys and tables.

A level covers the whole connection, not one table. Only the owner can delete
the connection, change its settings, back it up or share it further.

A shared connection appears in the other person's list. Its window shows who
shared it and at what level, and its fields cannot be changed.

A table can also be shared as a link: **Share this view** in the row of commands
above a table makes a link to that table with its filters and columns. A link
gives no access by itself. Somebody who opens it without access to the
connection can ask for it, and the request appears on the owner's
**Permissions** page and in their activity bell. The owner chooses the level
when approving it.

## Opening a catalog

Pressing a connection opens its catalog: what the source holds, level by level
or as a tree, depending on the kind of source. A catalog has a row of its own
commands at the top, and a menu of actions on what is ticked. The commands
depend on the kind of source and are described on its page.

Things that appear in every catalog:

- ticking a node and opening the actions menu acts on what is ticked, or on the
  level you are on when nothing is;
- **Details** says what a node is: its size, its dates, what it can be opened
  as;
- **Copy** and **Cut** pick nodes up, and **Paste** puts them where you are
  standing, in the same connection or in another one;
- opening a node opens it in a tab of its own in the work column, as rows, as a
  document, as an image and so on;
- the catalog can be duplicated beside itself, or paired with the catalog of
  another connection in one window, to move things between the two.
