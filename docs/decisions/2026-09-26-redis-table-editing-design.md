# Editing a table declared over Redis

Date: 2026-09-26. Decision: D173. Builds on D25 and D26 (the grid's editing
contract), D43 and D166 (rows added to a ticked table), D170 (tables declared
over Redis folders) and D172 (looked up by key).

## The problem

A declared table reads as rows and cannot be written: D170 left editing for
later. The hashes under it are ordinary Redis hashes, each of which the grid
can already edit one key at a time as `field, value`. Seen as the table a
person declared, the same change is one cell, and a new user is one row — and
rows from a CSV or a database table, pasted into it (D166), are what D166's
"Add rows to a table" already does for any source that takes rows.

## D173. A declared table is edited as its rows

What changes is always the hash a row is: the grid's contract, answered by the
folder's keys.

- **A cell is one field of one hash.** Typing a value writes that field;
  emptying the cell removes the field, which is how the table shows a field a
  hash lacks. `key` is not edited: it is where the row lives, and changing it
  would be moving a hash, not editing one.
- **A new row is a new hash**, `prefix` + the typed `key`, holding the fields
  given a value. The key is required and must be a name within the folder — a
  separator would put it in a folder below, outside the table — and must not
  be taken; a taken key is refused by name. A row with no field is refused:
  Redis keeps no empty hash, and an empty value is no field.
- **Deleting rows deletes their keys**, all of them or none.
- **Values are checked against the declared type** before anything is written:
  a number reads as a number, a boolean as true or false, a date and time as
  ISO 8601. Text takes anything. A value is at most 64 KB, the limit Redis
  editing already has. Every refusal names the cell, and nothing is written.
- **What was read is what is changed.** Each row carries a fingerprint of the
  values the page showed; an edit or a delete whose hash has changed since —
  another value, another type, gone — is refused as a conflict, the rule Redis
  editing already follows.
- **Emptying the last field a hash holds is refused**: Redis would remove the
  key, which is a delete, and a delete is its own command.
- **Adding many rows at once** — D26's paste, D43's import, D166's "Add rows to
  a table" from any source — checks every row and every key first, then writes
  all of them in one transaction.
- **Access is `write`**, as for any row. The declaration itself still needs
  `structure` (D170).

## Out of scope

- Renaming a key, moving a row to another folder.
- Writing a field the table does not declare.
- A time to live for a new row.

## Known deviations, accepted with it

- **Checked, then written.** Redis has no compare-and-set for a hash, so a
  change made between the check and the write is overwritten — the race
  Redis editing already accepts. For many new rows, a key created in that
  moment by somebody else gains the new fields.
- **The declared type is checked on write, not on read.** A hash that already
  holds `x` in a number column is shown as it is.

## Acceptance

- A cell edited in a Redis table changes that field of that hash; emptied, the
  field is gone; `key` offers no editing.
- A new row with a free key creates the hash; a taken key, a key with a
  separator, no key, or no field is refused and writes nothing.
- A value that does not read as its declared type is refused, and a paste of
  several with one bad value writes none.
- Rows deleted remove their keys; a row changed since it was read is a
  conflict, for an edit and for a delete.
- "Add rows to a table" from a CSV into a Redis table creates one hash per row.

Tests cover each of these against a real server, and in the browser a row
added, a cell edited and a row deleted in a Redis table.
