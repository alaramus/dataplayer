# S3

Amazon S3, or any store that speaks its API. You browse buckets and folders and
work with objects as with your own files: tables, SQL over files, the viewers
and search. It signs in with an access key. How connections work in general is
on the [Connections](connections.md) page.

## What you can see

- Buckets, and the folders and objects in them
- Tables in CSV, TSV, Excel and Parquet files, and in logs
- Documents, code, images, PDFs, recordings and the insides of zip archives
- Objects found by name, or by the text inside them
- SQL run over tables kept in objects

## What you can change

- Objects in a text editor
- The rows and columns of CSV and TSV files
- Objects and folders: create, upload, rename, delete, download
- Archives: pack objects into one, or unpack one
- Objects copied or moved between folders and connections
- Buckets: make one, or delete one with what it holds

## Connecting

The **Connection** page of the window asks for:

- **Endpoint**: the store's address, such as `https://s3.example.com`. Empty is
  Amazon S3;
- **Region**: empty is `us-east-1`;
- **Access key** and **Secret key**;
- **Bucket**: empty shows every bucket the key may list;
- **Folder**: where browsing starts inside the bucket;
- **Addressing**: auto is virtual-hosted on Amazon S3 and path-style elsewhere,
  which every compatible store accepts;
- **Verify the certificate**: switch it off only for a store whose certificate
  you made yourself.

An address such as `s3://reports/2026`, an Amazon S3 URL or
`https://host:9000/reports` pasted into **URL** fills the endpoint, region,
bucket and folder. The keys are never part of it.

The catalog of types shows a card for each provider: Amazon S3, MinIO,
Cloudflare R2, Backblaze B2, Wasabi, DigitalOcean Spaces, Google Cloud Storage,
Yandex Object Storage, VK Cloud, Selectel and Hetzner Object Storage. Every
card is this same form: it fills in what the provider always names the same and
says where to find the rest. None of them starts a server.

## The catalog and the objects

An S3 connection is browsed like a [Files](source-file.md) connection: the same
catalog, the same search by name and inside files, the same viewers and the same
SQL over files. The same actions too: **New folder**, **New file**, **Upload files**,
**Rename**, **Delete**, **Download**, **Archive**, **Extract**, **Copy**, **Cut**
and **Paste**.

How a store differs from a disk:

- A folder is the shared beginning of keys, `reports/2026/`. An empty folder is
  an empty object whose key ends in `/`, which is what the providers' own
  consoles make.
- A key that could not be a file name — one with an empty, `.` or `..` part, a
  backslash, or a drive such as `C:` — is not shown. It is still in the bucket.
- An object larger than 200 MB is not opened as a table, a workbook, an archive
  or in SQL: download it instead. Text, pictures, PDFs and recordings open
  whatever their size.
- A search inside objects skips those over 1 MB and stops after 32 MB in total,
  because every byte crosses the network.
- An object in an archive storage class has to be restored before it can be
  read.
- Renaming or moving a folder copies every object in it and removes the old
  ones: the store has no rename. Up to 10,000 objects are moved, copied or
  deleted at once; a larger folder is refused.
- A file saved over one that changed meanwhile is refused rather than
  overwritten.

### Buckets

When **Bucket** is empty, the top of the catalog lists buckets.

- **New folder** there makes a bucket, in the connection's region. Its name
  is 3 to 63 lowercase letters, digits, dots and hyphens, beginning and ending
  with a letter or a digit.
- **Delete** removes a bucket with everything in it, up to 10,000 objects. A
  bucket that keeps old versions of its objects is refused: empty it with a
  lifecycle rule first.
- A bucket cannot be renamed or copied, and no file is kept beside the
  buckets.
