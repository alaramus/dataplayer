# MongoDB documents as documents

Decision D295. After the MongoDB source's six slices (D283–D294), the user
opened "View as documents" and got "the source does not support editing
content": the `json` and `jsonl` representations open the file editor, which
asks for a file's source text, and MongoDB has no file. "View the definition"
failed the same way. Nothing in the client drew a `JsonContent` at all.

## What other clients do

Every MongoDB client compared — Compass, Studio 3T, Robo 3T, DBeaver,
DataGrip, NoSQLBooster — shows documents as trees and edits them; none is
view-only. All edit a whole document as Extended JSON text; Compass and Studio
3T also edit a field in the tree. Compass sends only the fields that differ,
not the document replaced.

## What was chosen

The user asked whether to edit whole documents as JSON or single fields in a
tree first. Both write the same thing — a field set or removed — so the route
takes a change as a list of paths from the start, and as the whole edited text
too, the source working out the paths. The first screen edits the text; a tree
that edits one field later sends the list.

Replacing the document with the text was rejected: relaxed Extended JSON
writes an `Int64` and an `Int32` alike, so a document saved whole after one
field changed could turn every other number into a different type without a
word. Comparing on the server, value by value as relaxed text, keeps what was
not touched as it is stored, and the comparison happens where BSON is, not in a
browser that would read a 64-bit number as a double.

Two new representation kinds rather than a flag on `json`: the panel a kind
opens is decided by the kind (D47), and a file's JSON is still the editor's.
`tree` is a source's own description, read only; `documents` is a relation
read whole, with its own route, because a page of documents needs the grid's
filters, order and row handles, which `read_content` does not carry.
