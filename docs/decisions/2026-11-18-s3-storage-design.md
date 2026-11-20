# S3 and compatible stores as a storage of the explorer

Decisions D379–D382. An object store is a tree of files only by convention:
keys with slashes in them. This source makes it one more storage under the
explorer (D150), so the catalog, the viewers, SQL over files, search, the
editor, transfers and the file actions are the ones the disk and SFTP already
have. One type, `s3`, reaches Amazon S3 and every store that speaks its API.

## Driver

boto3. Its client blocks, which is what a storage is asked to do (D151): no
hop back to an event loop, as SFTP needs. It is pure Python, so every
platform and Python 3.14 install it. It has `ListBuckets`, conditional writes,
multipart uploads and copies through s3transfer, and error codes that can be
reduced to a kind without reading a message. Every compatible store is tested
against it by its own vendor.

- **Checksums only where required.** Since 1.36 boto3 sends and checks CRC
  checksums by default, and several compatible stores refuse or mangle them.
  `request_checksum_calculation` and `response_checksum_validation` are
  `when_required`.
- **Only in its adapter.** `boto3`, `botocore` and `s3transfer` are imported
  by `adapters/s3` and nothing else; `.importlinter` says so.

Rejected:

- **obstore.** 5.5 MB against botocore's 16 MB wheel, with a synchronous API.
  But `object_store` is one bucket per store and has no `ListBuckets`, so a
  connection to every bucket a key can see is impossible, and its API is still
  0.x.
- **aiobotocore.** Asynchronous, which the storage would only bring back into
  a thread, and pinned to a narrow range of botocore that lags boto3.
- **minio-py.** Small and synchronous, but its project is archived with the
  MinIO server.

## D379. A key's path is a node id, and a bucket is a folder

- **Where browsing stands.** A connection names a bucket and a prefix inside
  it, or no bucket at all. With a bucket, the root is that bucket below the
  prefix. Without one, the root lists the buckets the key may see and a node
  id's first segment is the bucket.
- **Ids are paths.** A node id is the key below the root, judged by the one
  containment rule (`PathPlaces`, `stays_inside_root`). A key no such id could
  name again — an empty segment (`a//b`), `.` or `..`, a drive reference
  (`C:x`), a backslash — is left out of a listing, as SFTP leaves out a name
  the rule refuses. It is still in the bucket; it is not this source's.
- **A folder is a common prefix.** A listing asks with `Delimiter="/"`. An
  empty folder is a zero-byte object `name/`, the marker the consoles of every
  provider make, and New folder makes one. A folder exists while its marker or
  any key below it does. `entry` asks HEAD for the key, then lists one key
  below `key/`. `has_entries` answers yes for every folder, as SFTP's does.
- **Reading.** `open` reads by ranged GET at any offset, as SFTP's remote file
  does. A library that opens a path gets a copy (D152), within its 200 MB, so a
  CSV, a Parquet file or a workbook in a bucket is read by SQL like one on the
  disk. A search by content reads as little as on SFTP (`REMOTE_SEARCH`).
- **Facts.** Size and last modified from the listing; no permissions, no
  links, no access or creation time. `version` is the ETag.
- **Errors are kinds.** `AccessDenied`, `InvalidAccessKeyId`,
  `SignatureDoesNotMatch`, `NoSuchBucket`, an unreachable endpoint, a refused
  certificate and an archived object (`InvalidObjectState`, Glacier) each
  become a kind and a sentence. Neither the key id nor the endpoint's address
  is in what the caller reads: botocore puts both in its messages.

## D380. What an object store lacks is done another way or refused

- **No partial write.** Every write is a whole object, which is already how
  the explorer writes: staged, then published.
- **Writes are conditional.** Publishing under a name nothing holds sends
  `If-None-Match: *`; replacing the version a document was read as sends
  `If-Match` with its ETag, and a 412 is `VersionChanged`. A store that refuses
  the header (501, `NotImplemented`) is asked HEAD first instead, with the race
  that leaves; this is a known deviation, not an error.
- **Large objects.** A staged file goes up through s3transfer, multipart above
  8 MB. `incoming` (D168) is a multipart upload written part by part, 8 MB a
  part, so a transfer of gigabytes holds one part on this machine; an upload
  not published is aborted, so no orphaned parts are left to bill.
- **No rename.** A file is copied on the server and the original deleted;
  above 5 GB the copy is multipart. A folder is every key below it moved so,
  up to 10,000 objects; more is refused with a sentence. Neither is atomic: a
  move cut short leaves keys in both places, and that is a known deviation.
- **Copy is the server's.** A file or a folder copied within one connection is
  `CopyObject` per key and passes nothing through this machine, so the 200 MB
  ceiling of a copy through here does not apply; the 10,000-object ceiling
  does.
- **Removing** a folder deletes its keys a thousand at a time. `remove_empty`
  deletes the marker only when nothing else is below it.
- **Versions.** Only the current version is shown. In a versioned bucket a
  delete leaves a delete marker and the confirmation says the old versions
  stay. A version's history is a later step.
- **What has no counterpart is missing.** No permissions are changed, no links
  made, and a folder does not become a connection of its own: its draft would
  carry the key to the browser, as an SSH folder's would (`ConnectFolder` left
  out).

## D381. A bucket is made and removed in the catalog

When a connection names no bucket, the root is where buckets live.

- **New bucket at the root makes a bucket** (New folder until 2026-11-20, when a bucket became a kind of node of its
  own, `bucket`, so that the kinds an action applies to keep Rename off it). Its name is checked against the S3
  rules — 3 to 63 characters, lowercase letters, digits, dots and hyphens,
  beginning and ending with a letter or a digit, not an IP address — before
  anything is sent, and it is made in the connection's region
  (`LocationConstraint` outside `us-east-1`).
- **Delete at the root removes a bucket** with everything in it, within the
  10,000-object ceiling, under the explorer's usual confirmation, which names
  it as a bucket. A versioned bucket that is not empty is refused: its old
  versions would have to go too, and that is a lifecycle rule's job.
- **A bucket is not renamed**: S3 has no such call. Rename and Archive are not
  offered on a bucket, nor New file, Upload and Paste where buckets are; the
  storage says which places those are, and the explorer offers by it rather
  than by the kind of node alone. A bucket copied or moved becomes a folder
  of its name, and a move deletes it once empty.
- With a bucket named in the connection, the root is that bucket and these
  actions do not exist.

## D382. One form, a card per provider, nothing started here

- **The form.** Endpoint (empty for AWS), region, access key id, secret access
  key (`SecretStr`), bucket (empty for every bucket), prefix, addressing
  (auto, path, virtual) and whether to verify the certificate. TLS is the
  endpoint's scheme. Auto addressing is virtual on AWS and path everywhere
  else, which every compatible store accepts.
- **Connection strings** name the store and never a key: the endpoint, or
  `https://s3.<region>.amazonaws.com` on AWS. They first carried the bucket
  and the prefix too, `https://host:port/bucket/prefix`; that repeated two
  fields of the form, and erasing a part from the box brought it back, since
  the form merges what an address answers. A pasted `s3://bucket/prefix`
  still fills those two. The keys are typed apart, as an SSH password is.
- **Cards.** Every card is the type `s3` and the same form, filled with what
  its provider always names the same (D264, D377); none starts anything.

  | Card | Fills in | Says where to find |
  | --- | --- | --- |
  | Amazon S3 | no endpoint, virtual | an IAM access key |
  | MinIO | path | the server's address, usually port 9000 |
  | RustFS | path | the server's address, usually port 9000, and the credentials it was started with |
  | Cloudflare R2 | region `auto`, path | `https://<account>.r2.cloudflarestorage.com`, an R2 API token |
  | Backblaze B2 | | `https://s3.<region>.backblazeb2.com`, an application key |
  | Wasabi | | `https://s3.<region>.wasabisys.com` |
  | DigitalOcean Spaces | | `https://<region>.digitaloceanspaces.com` |
  | Google Cloud Storage | `https://storage.googleapis.com`, region `auto` | HMAC keys |
  | Yandex Object Storage | `https://storage.yandexcloud.net`, `ru-central1` | a static access key |
  | VK Cloud | `https://hb.ru-msk.vkcloud-solutions.ru`, `ru-msk` | account keys |
  | Selectel | | the pool's endpoint and region, S3 keys |
  | Hetzner Object Storage | | `https://<location>.your-objectstorage.com`, the location as region |

- **No service template.** MinIO, the obvious server to start here, stopped
  publishing images in 2025 and archived its repository in 2026; this product
  ships open-source servers only. MinIO stays a card, because servers of it
  are still running and connecting to one costs nothing.
- **The test server is RustFS** (Apache-2.0), configured by environment like
  MinIO was. It is in `compose.override.yml` behind `tools` and in CI, started
  by a step rather than a service container, and the tests that need it skip
  without it except under `--require-services`.
- **Sample files** for tests come from `explorer/samples.py`, one of every
  kind, put into a bucket the tests make.

## Tests

- Containment through the adapter and the API: `..`, an absolute id, a
  segment like `C:x`, a backslash; and keys made in the bucket with those
  shapes are absent from a listing.
- Errors: a wrong secret and an unreachable endpoint answer a kind, and
  neither the secret, the key id nor the endpoint is in the text.
- Conditional writes: a taken name, a version changed under an edit.
- `incoming` across several parts, and an aborted upload leaving none.
- Folders: an empty marker, a rename and a removal past the ceiling refused.
- Buckets: a bad name refused before a request, a bucket made and removed,
  what is offered where buckets are and on one, a bucket copied and moved
  into a folder.
- SQL over a CSV and a Parquet file in the bucket.
- Cards: their options against the form; connection strings parsed and
  refused.

## Rejected

- **DuckDB's `httpfs` reading the bucket itself.** It would read a large
  Parquet file without a copy, but D78 keeps the engine off the network with
  no extensions; a hole there is what that decision exists to close.
- **Presigned links for downloads.** A download through this server is what
  every other source does and what the download rules (D55) judge; a link
  straight to the store is a later step.
- **A template of another server** (RustFS, Garage, SeaweedFS) now. RustFS
  may get one later, as a card of `s3` like those of D377.
- **Cloud sign-in** — IAM roles, instance profiles, SSO. Keys only, as the
  hosted database cards sign in by password.
