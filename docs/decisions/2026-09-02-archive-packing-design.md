# Making an archive, and taking one apart

## Goal

Two things a file manager has and this source did not: pack a selection into
one archive, and expand an archive that is already there. Until now an archive
could be walked into (D53) and downloaded, and that was all — a folder of
twenty files could be sent nowhere as one thing, and a `.tar.gz` somebody
received could be read one entry at a time but never unpacked.

## Which formats, and why not the same set as browsing

Browsing is ZIP only, and stays that way: a tar has no central directory, so
listing it means reading it end to end and reading one entry means reading it
again (D53).

Packing and unpacking have no such requirement — both are one pass over the
whole file — so the tar family joins ZIP: `zip`, `tar`, `tar.gz`, `tar.bz2`,
`tar.xz`. Expanding also takes the short spellings (`.tgz`, `.tbz2`, `.txz`)
and the single-stream compressions (`.gz`, `.bz2`, `.xz`), which are one file
rather than a container and are expanded to that one file.

All of it is the standard library. Nothing is added to the dependency list to
open something a person receives by email.

## The rule about names is the rule this source already has

Nothing trusts a name written inside an archive. Every member goes through
`stays_inside_root`, the one containment rule of D8, and:

- **an archive holding a name that escapes is refused whole.** Every member is
  judged before anything is written, because somebody told "that was refused"
  must not be left wondering what landed first;
- **a tar holding a link is refused**, and so is anything that is not a plain
  file or a directory. `tarfile`'s own `data` filter runs as well as this
  source's walk — two rules, both applied;
- **symbolic links are not packed either**, which is what the download of a
  selection already does.

Both ceilings are the ones a download of a selection is held to: ten thousand
entries and two gigabytes. Unpacking is held to them by what the archive
declares before a byte is written.

## Two actions, and one of them takes a set

`create_archive` is a set action (D68): five files chosen for one archive are
one archive, and sending them one at a time would make five. It writes beside
the selection, into the folder they share, and refuses a selection spread over
several folders. The suffix follows from the chosen format rather than from
what was typed, and a name already taken gets the next free one, exactly as a
new folder does.

`extract_archive` is repeated rather than taken as a set: three archives are
three expansions, and one being refused says nothing about the other two. By
default it makes a folder named after the archive; turned off, it puts the
contents beside it. A refused expansion takes that folder with it, so nothing
half-extracted is left with a name somebody will look for.

Both are built beside their destination and moved into place, which is how
every write in this source already behaves.

## What the client needed

Nothing. The menu, the form with its name field and its format select, the
confirmation and the set transport all came from what the source declares —
which is the point of D9 and D56, tested here by a feature that reached the
screen without a line of client code.

## Rejected alternatives

- **Extracting into the folder by default.** Twenty files landing beside the
  archive is the thing people undo.
- **Refusing anything but ZIP.** The formats people actually receive are the
  reason this exists.
- **Streaming an expansion without reading the manifest first.** Then a refusal
  halfway leaves half an archive on somebody's disk.

## Deferred

Encrypted archives, RAR and 7z (neither is in the standard library), and
choosing where an expansion goes beyond "here" or "a folder of its own".
