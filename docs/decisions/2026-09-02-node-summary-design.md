# A node describes itself

## Goal

The first item of phase 3.5: a summary of one node — size, kind, times, what it
can be opened as, and for a text or tabular file what is in it. Every file
manager has it under Properties, and this one had nowhere to put the question.

## What shape it takes

The roadmap posed the shape as the thing to settle first, because the two
obvious homes are both wrong.

- **An action returns a message.** `ActionResult` is what happened, and a
  summary is not something that happens. An action that changed nothing and
  answered a screenful of facts would make every consumer of the action
  vocabulary — the menu, the confirmation, the preview, the audit line — treat
  a question as a command.
- **A representation is a viewer.** `read_content` answers with the node's own
  bytes in one bounded native shape (D47). A summary is *about* the node, not
  *of* it: adding it as a representation would put "About" in the same list as
  "View as text", where the first entry is what opening the node means.
- **A relation model is the shape of something tabular.** It was the closest
  fit and still wrong: half of `RelationModel` — schema, owner, persistence,
  constraints, indexes — is vocabulary a folder does not have, and the nodes
  that most need a summary are exactly the ones that answer no relation model.

So it is a fourth question with a capability of its own, and the answer is
that four questions about a node is the honest number:

| Question | Capability | Answer |
| --- | --- | --- |
| Show me its rows | `SupportsFetch` | a page |
| Show me what is in it | `SupportsContent` | one bounded representation |
| What shape is it | `SupportsRelationModel` | columns, keys, indexes |
| **What is it** | **`SupportsNodeSummary`** | **`NodeSummary`** |

## Decision

**D75. A node describes itself, and that is neither a viewer nor an action.**
The statement, its consequences and the known deviations are in
[the source contract](../architecture/sources/contract.md).

`CatalogNode.summarizable` says which nodes answer it, exactly as `describable`
says which answer a relation model. The alternative — the client deciding from
the kind that a file has a summary and a table does not — is the client
deciding what a source can answer, which is the rule D2 exists for.

## What is in it

Flat and shared, because every node has them: `size_bytes`, `modified_at`,
`accessed_at`, `created_at`, `permissions`, and `representations` — the
catalog's own ordered list, so "what can this be opened as" is computed once
and read in two places.

`contents` is a discriminated union, and its members are the readers this
source already had:

| Format | Where the facts come from |
| --- | --- |
| text, Markdown, JSON, JSONL | one pass over the bytes, written for this |
| CSV, TSV | the `csv` parser, so a quoted line ending is not a row |
| Parquet | the footer, as `ParquetDataset` — D51's own model |
| a worksheet | the sheet list, as `WorksheetDataset` — the same |
| a workbook | how many sheets, and how many are hidden |
| a ZIP | the central directory, inflating nothing |
| an entry | what the archive declares about it |
| PNG, JPEG | the image header, no raster decoded |
| audio, video, PDF | D52's container probes |
| anything else | nothing, and no invention |

The one new reader is the text pass. It is chunked, so neither a file nor a
line is held whole; it looks for `\r\n`, `\n` and a lone `\r`, because "which of
them is in this file" is one of the things being asked; and it decodes
incrementally, so a file that is not UTF-8 says so rather than being decoded
with replacements and called text.

## Ceilings, and saying when one was hit

A summary must not become a job. Two numbers hold it:

- **32 MB** of a file is read through. Past it, `lines`, the longest line and
  the line endings are absent and `not_counted` says why — never a zero, which
  would be a count.
- **2000 entries** in a folder, which is the number its own listing refuses to
  go past. The same number in both messages rather than a second opinion about
  how big a folder may be.

## What a misleading name does

The catalog classifies by filename and says so as a known deviation of D47: a
`.zip` holding something else advertises a walk it will later refuse. The
summary is where a reader finally meets that. Bytes that are not the format
their name promises leave `contents` empty and put the reader's own refusal in
`notice`, beside facts that are still true — the size, the times, the mode.

The refusal is the reader's own and never the operating system's: every message
that can reach `notice` is written in this repository, while an `OSError`
becomes "This file could not be read", because its text carries the path of the
file.

## On screen

A panel of the work column, opened from the catalog for exactly one ticked
node. A panel rather than a floating window because it is a read of a source
that can fail, be re-read and be kept open beside the thing it describes —
which is what every other read of a source in this application is, and what the
window host, which holds forms and questions, is not.

It is opened from a line of the catalog's one menu, where Copy and Cut moved to
join it: what can be done with a ticked row is asked in one place, and the
alternative is a row of icons that grows with every verb the client gains. The
client's lines carry a `client:` prefix, because one menu now carries two
vocabularies and a source names its actions with identifiers.

It renders through one pure function from the typed answer to labelled facts,
next to the one D51 already had for a dataset — which it calls for the two
members it shares with it, rather than writing the Parquet facts a second time.

## Deliberately not in this slice

- **PostgreSQL.** A table's size on disk, its owner and when it was last
  analysed are a real summary and a different set of facts; the capability is
  there for it, and 501 is the honest answer until it is written.
- **Counting inside an archive.** Expanding an entry to count its lines costs a
  temporary file of up to 32 MB (D53).
- **A recursive folder size.** That is a walk of a whole tree, which is a job
  rather than a request.
- **A certificate, EXIF, a checksum.** The old screen parsed `.pem` and `.crt`
  in the browser. Each is a reader of its own and belongs to whoever asks for
  it, not to the slice that makes the question askable.
