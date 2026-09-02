# Copying and moving files

## Goal

The one thing every file manager has and this source did not. A file could be
renamed, deleted, downloaded, archived and expanded, and could not be put
somewhere else.

## Why not a destination field

The obvious shape is an action on the selected nodes with a `destination`
parameter. All three ways of filling that field are bad:

- **Typing a path.** Asking somebody to type a folder they are looking at.
- **A select of every folder.** The source would have to walk its whole tree
  to answer what a menu is, on every listing of the vocabulary, three times per
  catalog interaction.
- **A tree picker in the dialog.** A second catalog inside the first, with its
  own paging, filtering and permissions.

The shape people already know avoids all of it: pick things up here, walk to
where they go, put them down. The destination is where the user is standing,
which the source already knows how to be told — `acts_on: "children"`, the
same as creating a folder or uploading.

## Decision

**Copy and Cut are the client's, Paste is the source's.**

Copy and Cut change nothing: they remember a selection and a verb in
`features/catalog/clipboard.ts` — module-level state, like the share intent
beside it. Nothing is sent, nothing is locked, and a person who changes their
mind has changed nothing.

`paste` is an ordinary declared action of the file source, on a directory's
children. What was picked up travels in the request rather than being
remembered by the server: a selection held for ten minutes in a browser is not
something the source should be keeping, and every id in it is judged on arrival
by the same containment rule as any other path (D8).

**The form fills itself by purpose, never by name.** The action declares two
hidden fields, `x-ui-purpose: clipboard-nodes` and `clipboard-mode`, and the
dialog fills them from what is held. The client learns that a field wants the
selection — not that the action is called paste, and not what pasting means.
That is the same arrangement `node-name`, `grouping` and `file-conflict`
already use.

Two consequences fall out of it:

- **Copy and Cut are drawn only where a source has somewhere to put things**,
  which is: only where its vocabulary contains a command with a
  `clipboard-nodes` field. A database offers neither.
- **A command that needs the clipboard is disabled while it is empty**, and
  says what it would paste while it is not.

## What the source does with it

Both verbs go through one implementation, bounded by the ceilings an archive is
bounded by: ten thousand entries and two gigabytes, counted before anything is
written. A folder cannot be put inside itself or inside anything it holds —
checked on the resolved paths, because two ids can name one place and only one
of them looks like a prefix of the other. A name already taken is refused,
replaced or kept beside the other, which is the conflict vocabulary uploads
already have.

A move names both ends in `reload_node_ids`: the folder that gained the nodes
and every folder that lost one. The clipboard is forgotten once its contents
land, because offering to paste a file that has just been moved away is
offering a refusal.

## Rejected alternatives

- **A server-side clipboard.** State with an owner, a lifetime and a failure
  mode, for something a browser already remembers perfectly well.
- **Drag and drop between catalogs.** A gesture worth having, and a different
  slice: it needs a drop target per row and an answer about dragging between
  two connections.
- **Copy and Cut as declared actions.** They do nothing, so a round trip to
  learn they may be pressed is a round trip for nothing.

## Deferred

Pasting between two connections of the same source type, a progress report for
a large copy, and undo.
