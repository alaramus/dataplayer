# Walking into an archive

## Problem

A `.zip` in personal storage is a directory that happens to be one file. Today
it is opaque: it can be downloaded and nothing else, so reading one file out of
it means downloading the lot, unpacking it somewhere and opening it there.

Every part of that is already built. D51 made a file that holds nodes into a
container the catalog walks into. D49 made a source-declared download over
selected nodes. D47 gave every node its ordered representations. What is
missing is the archive itself, and the three questions the roadmap refused to
implement before they were answered: containment, decompression limits and
symbolic links.

They are the right three. An entry name is text written by whoever built the
archive — the classic zip-slip is an entry called `../../etc/passwd`. A
declared size is text too, and a zip bomb is nothing but a small file that
claims to be small and is not. And a symbolic link inside an archive points
wherever its author wrote, which is not a place this source has agreed to look.

## Containment: the same rule, for the third time

An entry name is judged by the rule every other path is judged by — the one in
`FileSession`: a relative path whose every segment is a plain name by the rules
of both platforms. A name typed into a form, the filename inside a multipart
upload and the name of an entry inside an archive are the same kind of string,
and the point of that rule is that there is only ever one of it.

An archive holding a name that fails it is refused whole, with the name in the
message. Listing the good entries and quietly dropping the bad one would be a
second rule — "mostly contained" — and a reader would have no way to know that
what they are looking at is not what is in the file. The archive stays
downloadable, as every opaque file does.

Node ids therefore carry the entry path, because the path has passed the rule
that makes a path safe. Resolution splits an id at the longest prefix that
names a container file on disk, so `notes/backup.zip/docs/readme.md` is the
document inside the archive inside the folder, and a directory that happens to
be called `backup.zip` keeps its ordinary meaning.

## Limits: nothing is inflated to answer a question that does not need it

Listing reads the central directory, which is metadata: entry names, declared
sizes and dates. No byte is decompressed to build the tree, so the only bound
listing needs is on how many entries there are — 10,000, the same number D49
refuses to archive past.

Reading one entry expands it into a temporary file, bounded at 32 MB, and the
viewer that asked reads that file with its own ceiling on top. Two checks, not
one: the declared size must be under the ceiling **before** anything is read,
and the bytes that actually arrive are counted as they are written. The second
turned out to be belt and braces — `zipfile` stops at the size the central
directory states, so an entry holding more than it admits to fails its own
checksum there, and what mattered was reporting that as a damaged entry rather
than as a file that is not an archive. The count stays because the ceiling
should rest on something this module can see. The temporary file goes away with
the read that made it.

Expanding rather than streaming is a deliberate simplification: every reader in
this source reads a path, and a bounded temporary file lets all of them — text,
Markdown, JSON, JSONL, the image viewer and the table projection — work inside
an archive without a second implementation of each. What it costs is one write
per open, and paging a large CSV inside an archive expands it once per page.

What is not offered inside an archive is offered nowhere in it: a Parquet file
and a workbook seek around their own bytes, media and PDF are streamed by range
(D52), and a nested archive would need a reader inside a reader. Those entries
are listed, with their size and date, and declare no viewer — which is what
every file with no viewer already does.

## Symbolic links: listed, never followed

A zip entry can carry unix mode bits, and one of them says the entry is a link
whose content is the path it points at. It is listed — it is in the archive,
and hiding it would be a lie about what the file holds — and it declares no
viewer and cannot be read. This source does not follow a link out of its root
on disk (D8) and does not follow one written inside a file either.

An encrypted entry is refused for the same shape of reason: it is listed, it
states its size, and reading it needs a password this source does not take.

## An entry is a node of its own kind

`entry` joins `dataset` as a kind of member: a node inside a container file.
Directories inside the archive are entries too — `has_children` tells them
apart — because a synthetic folder is not a directory on disk and must not
accept a new folder or an upload into it.

Which actions apply is decided, as always, by the kinds each action names.
Rename, delete, new folder and upload name `file` and `directory`, so an entry
is out of all four without a rule of its own. Download names `entry` as well,
and the file source streams one entry's decompressed bytes; asked for a
directory inside an archive it refuses, because building a zip out of a zip is
a different result and this slice does not decide what it should be.

## What is deliberately absent

- **Only ZIP.** A tar has no index: listing it means reading it end to end, and
  every entry read means reading it again. That is a different contract, not
  one more extension in a set.
- **Nothing is written into an archive.** No editing, no adding, no removing.
  The editor still opens an entry, because refusing would take the reading away
  with the writing: the document arrives unwritable with the reason, through
  the channel D48 already uses for a file too large to edit.
- **No extraction to the personal directory.** Unpacking an archive into a
  folder is an action with its own containment story, and it belongs beside
  upload rather than beside browsing.
- **No password prompt**, and no archive-wide "expand all".

## Tests

Backend: an archive listed as a tree, one level at a time, with directories
synthesized from entry paths and no entry lost; an entry name that leaves the
archive refusing the whole listing; an entry count over the ceiling refused; a
declared size over the ceiling refused before reading, and an entry holding
more than it declares refused as damaged; a symbolic-link entry listed with no
viewer and refused when read; a Markdown document, a text file, an image and a
CSV read through their ordinary viewers; an entry opened in the editor
unwritable, with its own language, and refused when written; the path to an
entry walking through the archive; an entry admitting download and no other
action, and one entry downloaded on its own; the ranged stream refused inside
an archive; and a directory on disk named like an archive keeping its meaning.

Frontend: an entry is a leaf that opens its representation, an entry directory
is walked into. End to end: an archive is opened from the catalog, a document
inside it is read, and the entry is downloaded on its own.
