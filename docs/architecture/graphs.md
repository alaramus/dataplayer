# Graph visualization

Read this before changing graph documents, graph rendering, layout or a feature
that turns source metadata into a graph.

Decisions here: D97.

## D97. Graphs have a domain-independent document and two presentations

`shared/graph` renders nodes, rows/ports, edges and groups. The graph document
contains no table, database, connector or API types. Domain modules supply
presentation data and handle activation actions. The first producer,
`features/relationships`, maps existing relation models and declared foreign
keys; composite keys retain all column pairs in a single relationship. It also
draws the references a person declared (D106) that touch a relation it read,
in a colour of their own and without a direction, since neither end is the
key. A far end the selection does not hold is read from its own connection and
drawn as a card of it, grouped under that connection's name and keyed with it,
because two connections can hold the same id.

2D and 3D share the document, selection and filters. They keep separate node
positions and cameras. A 2D diagram opens no smaller than 75%, where a row's
11px is still read, from its top left corner when it is larger than the
panel; Fit shows the whole of it at whatever size that takes (D187). Moving nodes changes view state only; this slice has no
edge authoring or source mutation. Controlled interaction events and a separate
view-state type leave that possible without introducing a second graph model.

The catalog's actions menu opens a diagram for checked describable nodes, or
for the current filtered list if none are checked; the line is disabled, not
hidden, while that set is empty or larger than one diagram holds. A node that
opens and holds nodes of its own — a workbook — is drawn as the relations
directly inside it, grouped under its name. The command is offered only when
the source type has the `relationship_graph` capability, which requires both
relation models and node paths; the current rows never decide whether the
source describes relationships. The panel tab names the connection and the
size of the set, so the view itself carries no standing bar of its own. The
explicit set lives in its workspace descriptor. Loading is limited to 100
relations and four concurrent reads.
Failed reads and references outside the set appear as distinct placeholders.
Only outgoing foreign keys of loaded tables are claimed; unseen incoming
references are not inferred. Graph bounds are 300 nodes, 5,000 rows/ports and
1,000 edges; oversize input is refused without truncation.

Dagre lays out the 2D cards. SVG edges attach to fields or node headers.
The 3D layout starts from Dagre's sketch, seeds depth by stable node identity,
then runs d3-force-3d with link, charge, collision, center and weak sketch
forces. Nodes can move in all three dimensions rather than staying on fixed
group planes. Collision treats each table as a sphere around its center; it
does not guarantee that every line misses every table box. The simulation runs
for a bounded number of ticks in the layout worker, not on every frame.
Existing untouched flat 3D layouts are recalculated once while
manually moved positions remain as they were. Three.js supplies the 3D scene
and camera controls. Selection, neighboring objects, search and details are
available in both modes. Rendering and input
follow the actual panel lifecycle, including detachment and minimization;
WebGL absence leaves a usable 2D mode. Theme colors and layers use the existing
UI tokens. Source text is never injected as HTML.

TanStack Query owns fetched metadata. Only validated, versioned UI state is
stored locally, per user, connection and explicit node set. Refresh preserves
positions of surviving nodes. Source changes never become layout edits, and
layouts never become schema changes.

A producer may draw on the 2D canvas without the viewer, as pipelines do
(D175–D178), and then owns the positions and the camera. The canvas takes a
producer's commands in a card's head, where a press neither drags nor
selects; an icon, a struck-out state and a not-yet-made state on a row; whether a selection fades
what it does not touch; labels written over the edges, a label that would
cover another moved along its own line or stacked beside its middle, a press
on one selecting its edge; an edge's tone — at work, done, failed, passed
over, or a line of a second kind — a number before its label, and a hint over a number drawn in the
caution colour; and, when it is asked to, a row dragged onto a row of another
card, which it reports as the two joined and never joins itself. The viewer offers `node-actions` for a
selected node and `edge-actions` for a selected edge, and names the other
end and the direction of each connection of a selected node.

Spec: [A graph viewer with 2D and 3D presentations](../decisions/2026-09-04-graph-viewer-design.md)
