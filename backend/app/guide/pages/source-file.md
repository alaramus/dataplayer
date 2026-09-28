# Files

Your personal storage on this server: a folder of your own that nobody else
reaches unless you share a connection to it. You browse folders, open files in
the viewer that suits them, edit them, and move files in and out. How
connections work in general is on the [Connections](connections.md) page.

## What you can see

- Folders and files, and what each one is: its size, its dates, its format
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

The only field is **Path**: the folder inside your personal storage that the
connection opens on. `/` is the top of your storage, `/reports/2026` a folder in
it. Nothing outside your storage can be reached.

**Connect folder**, in the catalog's actions menu on a folder, makes a new
connection that opens on that folder.

## The catalog

- The path of the level you are on is shown at the top. **Copy the path of this
  level** copies it, in the form the **Path** field takes.
- **The top of this connection** returns to where the connection opens.
- The filter box narrows the level by name.
- The search button next to it looks for the same words in every folder below,
  by name. Hold **Shift** while pressing it to look inside the files instead;
  the first time, it says what that costs and asks. A match shows the line it
  was found on. **Back to the folder** leaves the results.
- Pressing a file opens it in a tab. Pressing a folder, a workbook or a zip
  archive walks into it.
- **Details**, in the actions menu, says what a file or folder is: its size,
  its dates, its permissions, what it can be opened as, and what its format
  says about itself (the columns of a Parquet file, the sheets of a workbook,
  the length of a recording, the size of a picture).

## Opening files

A file opens in the viewer that suits it. Where there is more than one way to
open it, the others are offered above it.

- **CSV and TSV** open as tables. Every column is text.
- **Excel workbooks** (`.xlsx`, `.xlsm`) open on their first visible sheet. The
  other sheets are along the foot of the grid, where a spreadsheet has them.
  Formulas show the value last saved in the file.
- **Parquet** opens as a table with the column types the file declares.
- **JSON** and **JSON lines** open as text, and **View as table** turns them
  into rows.
- **Logs** (`.log`) open as text, and **View as table** splits each line into
  its time, level and message.
- **Markdown** opens as a document, with a table of contents, code, maths,
  charts and diagrams. **Export** saves it as an HTML page or prints it.
- **Text and code** open in the editor with highlighting.
- **Images**, **PDF**, **audio** and **video** open in their own viewers. A PDF
  can be searched.
- A **zip archive** is walked into like a folder, and the files inside open
  like any other, read only.

Tables from files are read like any table in the grid (see
[PostgreSQL](source-postgres.md) for the grid itself), with two differences: a
file cannot be sorted, and a filter only matches a value exactly.

## Editing

- A text, JSON, JSON lines or Markdown file opens in the editor. **Save** writes
  it back. A JSON file must still be valid to be saved.
- If the file changed since you opened it, saving is refused and nothing is
  written. **Reload file** reads it again.
- Files up to 4 MB can be edited. A larger file opens read only and says why.
- In a CSV or TSV table you can change cells, insert rows, delete ticked rows,
  and add, rename or drop columns from **Structure**.

## Files and folders

The actions menu of the catalog offers, on the level you are on or on what is
ticked:

- **New folder**, **New file**, **Upload files**. An upload says what to do
  with a name already taken: stop, replace the file, or keep both under a new
  name;
- **Rename**, **Delete**. There is no bin: a deleted file is gone;
- **Download**: one file as it is; a folder, or several ticked files, as one zip;
- **Archive**: pack what is ticked into a zip, tar, tar.gz, tar.bz2 or tar.xz;
- **Extract**: unpack an archive here, or into a folder of its own;
- **Copy** and **Cut**, then **Paste** where you want them. This works between
  folders of one connection and between connections, including SSH servers.
  Pasting a table from a database into a folder saves it as a CSV file.

A copy between connections runs in the background. The activity bell shows how
it is going and can stop it.

## SQL over files

**Open as a query** above a table, or **New query** in **Queries** on the left
rail, starts a SQL console on this connection. A table is named by its path in
double quotes, such as `SELECT * FROM "sales/2026.csv"`. CSV, TSV, Parquet, JSON,
JSON lines and log files can be queried and joined; Excel sheets cannot yet.
Nothing a query does is written back to the files.

## Limits

- The editor holds files up to 4 MB.
- A search inside files skips files over 8 MB and stops after reading 256 MB.
- A folder lists at most 2000 entries.
- A file inside an archive is read up to 32 MB.
- A download or an archive holds at most 10,000 files and 2 GB.
