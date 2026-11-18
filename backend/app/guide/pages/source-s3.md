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

## The catalog and the objects

An S3 connection is browsed like a [Files](source-file.md) connection: the same
catalog, the same search by name and inside files, the same viewers and the same
SQL over files. **Download** fetches an object, or a folder as an archive.

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
