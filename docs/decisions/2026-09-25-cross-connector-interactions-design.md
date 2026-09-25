# Interactions between connections

Date: 2026-09-25. Status: proposed for implementation. This specification
describes intended behavior; the current single-connection paste remains as
documented in D74 until the new path is implemented.

## The problem

A person can copy a file in the local explorer and paste it into another folder
of the same connection. The SSH explorer presents the same folders and file
actions, yet Paste refuses the held file because its node id belongs to another
connection. The person should be able to copy an object, visit a destination,
and use Paste whenever that destination can accept it. They should not need to
know which adapter implements either end.

There is also a discovery problem. A person looking at two connections cannot
tell which operations are possible between them without trying menus. A paired
view should show the possibilities for the selected source objects and the
current destination. A graph of possible connections and a pipeline editor are
later presentations of the same information, outside this slice.

## One answer about a pair

The application asks what interactions apply to `(source connection, source
nodes, destination connection, destination place)`. Both node ids remain opaque
and are always accompanied by their connection ids. A connection type or its
category alone is insufficient: a file and a directory in one explorer, or a
writable and a read-only destination, can answer differently.

The answer is a bounded list of typed offers. Each offer has a stable operation
code, title, direction, availability (`available`, `unavailable`, or `checking`),
and a human-readable reason when unavailable. An offer also describes whether
it needs choices or confirmation before execution. The server computes the
answer from source and destination capabilities and current state; the client
does not maintain a matrix of adapter-type pairs. The same answer drives Paste,
the paired view, and a later graph. A displayed offer is information, never
authorization: execution resolves both ends and checks availability again.

The interaction belongs to the application layer that already coordinates two
connections for D43. An adapter describes what it can supply or accept and
operates only on its own nodes. It does not import another adapter or interpret
another source's id. A transfer implementation joins a compatible producer
and consumer through a typed intermediate representation. Representations are
introduced as actual interactions require them: file bytes with metadata for
file copy, rows and columns for row transfer. A universal conversion format or
all-pairs registry would invent semantics that the sources have not promised.

Offers distinguish **copy** from **move** and **conversion**. Copy leaves the
source intact. Move deletes the source only after destination publication has
succeeded and must say when a failure leaves both copies. Conversion (for
example CSV rows becoming a relation) names its resulting object and any
limits or loss of structure. Matching capabilities never silently turns a file
Paste into a table import or a move into a copy.

## Clipboard and Paste

Copy and Cut remain client-side intent. The clipboard records the source
connection id, opaque node ids, mode and a short display label; it contains no
credentials and does not contain the file bytes. It is not tied to the catalog
panel where it was created. A destination asks for offers with that intent and
its current container. Paste is enabled only when an applicable paste offer is
available. An empty clipboard, missing permission, disabled connection,
incompatible place or unready source produces a disabled control with an
explanation. While the answer is being checked, the control does not claim the
operation is impossible.

Paste of a copied file into a writable folder means copying that file under
the same name, whether the folders are in one connection or two. The first
cross-connection pair is the local explorer and SSH explorer, in both
directions. A file or selected files are supported first; directory trees and
cross-connection Cut require their own failure and recovery rules and are not
part of the first delivery. Existing same-connection copy and move keep their
current behavior. The destination's existing conflict choices (refuse, replace,
or keep both) remain explicit where needed; the client never chooses replace
merely because a name exists. The destination validates the name and publishes
the staged bytes by its own rules. The source validates every node when read.

The transfer checks read access to the source and write access to the
destination separately. It checks both again when the command runs, including
connector state and source-specific restrictions. A stale clipboard may fail
with a safe, specific explanation. It must never send source credentials to
the browser or route data through a browser download and re-upload. Bytes pass
through the application server in bounded chunks. A file larger than the
existing remote-view cache ceiling is not thereby ineligible for transfer;
transfer needs its own streaming limit and resource policy. The destination
does not publish a partial file. A batch reports each file's outcome, including
those not attempted, and refreshes the branches actually changed. No
cross-source transaction or undo is implied.

Long transfers follow D81 and D95: the request starts owned work, returns a
job, and the Processes surface reports bytes or items where they are known,
failure and cancellation. Cancellation stops at defined boundaries, cleans
staged output, and reports already published files. A resumable transfer is a
separate feature. The implementation must set and test concrete size, batch,
concurrency and temporary-space limits before exposing the operation.

## Paired view

A person can open two existing catalog views side by side and designate one as
source and the other as destination. The catalogs keep their ordinary
navigation, selection, permissions and panel lifecycle. The interaction area
between them names both ends and lists available and unavailable offers with
reasons. It updates when either selection, destination folder, connection
state or clipboard intent changes. A direction switch exchanges the roles; it
does not suggest that every offer has an inverse. The list is based on the
current objects, not merely on the two adapter type names. With no selected
source objects it explains what to select; it does not guess from all objects
in the catalog.

Choosing an offer opens only the choices it needs, then runs the same command
used by Paste. Dragging selected objects from one catalog to the other may
later select an offer, but a drop must never invent a conversion or bypass the
offer's confirmation. The paired view is an aid to discovery, not a second
transfer engine. Its placement within the existing workspace and exact panel
controls should be settled in a focused UI design before implementation.

## Relationship to existing operations

- D74's source-owned Paste continues to handle same-connection file operations.
  Cross-connection Paste is resolved by the application. The client asks one
  availability service and does not branch on whether the connector ids match.
- D43 row import and D45 creation of a relation from a file already coordinate
  or imply two ends. Their data semantics, limits and forms stay as specified.
  They can publish interaction offers after the common answer is in place;
  they are not rewritten into a generic byte copy.
- D97's graph document can later render offers as directed edges, with a
  separate domain producer. A possible transfer edge is not a D106 declared
  reference between data and is not evidence that a transfer happened.

## Delivery and acceptance

1. Define typed source and destination capabilities and the pair-offer answer
   with explicit unavailable reasons; keep type dispatch out of the client.
2. Implement local-file to SSH-file copy and SSH-file to local-file copy through
   the same transfer command. Preserve the source, destination publication
   rules and conflict choices. Integrate cross-connection Paste.
3. Add the paired catalog view over the same offer and execution paths.
4. Expose existing row-oriented interactions as offers only after their exact
   destination choices and limits can be represented without changing their
   meaning.

Acceptance examples: copying a local file enables Paste in a writable SSH
folder and produces an identical file; the reverse direction does the same;
an unwritable or disabled destination explains why Paste is unavailable;
changing selection or destination changes the paired list; a revoked grant
between discovery and execution prevents transfer; a failed or cancelled
transfer leaves no partial destination file; a name conflict never silently
overwrites an existing file. Tests must cover these cases at the capability,
API and UI boundaries. Validation commands are run only with the user's
explicit approval, per AGENTS.md.

## Deferred

Cross-connection move and directory trees, drag and drop, transformations,
pipeline authoring, a graph of possibilities, background discovery across all
connections, transfer resumption and durable transfer history. Each needs
semantics beyond the first file-copy path; none is implied by the pair offer.
