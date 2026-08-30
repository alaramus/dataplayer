# Exporting every matching row

## Problem

D28 downloads one bounded page. Its implementation may hold that page while it
writes CSV because the fetch contract has already capped it. Repeating the same
shape with a larger limit is not a whole-relation export: it only moves the
failure point, fills application and browser memory on the way, and teaches a
bounded read to mean two opposite things.

The grid needs two honest scopes. **Current page** remains D28. **All matching
rows** keeps the current filters, ordered sort and visible columns but drops the
page offset and limit. With no filters, that second scope is the whole relation.

## The source owns the stream

`SupportsExport` is independent of `SupportsFetch`. Its `export_rows` method
takes a node, filters, sort and an ordered list of columns, and returns an async
iterator of `ExportBatch`. A batch is bounded to 500 rows. The contract has no
unlimited list and no page ceiling disguised as a larger number.

The distinction is real rather than nominal. Repeated offset fetches can see
different versions of a changing relation, repeat the cost of reaching every
offset and still assemble an unbounded answer outside the source. An export
capability instead lets a database use one cursor and one source snapshot, an
object store use its streaming body, and a source that cannot do either say so.

The first implementation is PostgreSQL. It validates every selected, filtered
and sorted column against the relation before composing SQL, then reads one
query through a server-side cursor. Rows cross the adapter boundary in the same
lossless text representation as D23. The current stable ordering remains the
query's ordering; no raw expression enters from the client. The file adapter
does not claim this capability in this round: downloading an original file and
exporting a tabular interpretation of it are different operations, and file
downloads belong to Phase 1.4.

## CSV belongs between sources and storage

The adapter streams rows, not CSV. CSV is still the platform representation
settled by D28, including UTF-8 with a BOM, visible-column order, and an empty
unquoted field for SQL null while every present value is quoted. Keeping that
encoding outside PostgreSQL prevents every future streaming source from
inventing a different download format.

The connector layer writes each batch into a `.part` file under the caller's
`downloads/<connector-id>` directory. Only a clean end of the iterator renames
it to `.csv`; a refusal, upstream failure or cancellation removes the partial
file. Memory is bounded by one adapter batch and one encoded CSV batch. The
finished file remains in personal storage exactly as a page download does.

This is one request, not a durable job. It has a loading state and cancellation
through request cancellation, but no resumability, background progress or
retention record. Those require the job lifecycle deferred to Phase 4. Disk
capacity and upstream timeouts can still refuse an export; neither is hidden by
a truncated success.

## The browser must not rebuild the buffer

An authenticated XHR with `responseType: blob` would collect the finished CSV
in browser memory and undo half of the design. The export request therefore
answers only after the atomic file exists, with its filename, row count and a
short-lived signed URL naming that exact file. A normal anchor follows the URL,
so the browser downloads the response directly to disk rather than through a
JavaScript blob.

The ticket is a bearer capability, scoped to one user directory, connector and
filename and valid for one minute. It is issued only after the caller has read
access to the source. Possession during that minute is sufficient to read the
already-created copy; the ticket cannot name another path, and an invalid,
expired or missing-file ticket answers as not found.

## Interface and source answers

Download opens a small scope dialog instead of immediately assuming a page.
Current page is always offered once a page exists. All matching rows is enabled
only when the fetch answer says the adapter has `SupportsExport`; otherwise it
stays visible with the source's reason. Both scopes use the visible columns in
their displayed order. The all-matching request uses the committed filters and
sort, never an editor value the source has not accepted.

The page path and its existing tests remain intact. The new path is additive:
a source without streaming export still downloads the visible page exactly as
before and answers 501 if the whole-export endpoint is called directly.
