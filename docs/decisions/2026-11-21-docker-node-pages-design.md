# Docker node pages and opening

Decision D423. Docker's containers, images, volumes and networks open as their
own document views. The source publishes related table pages in the view
response, and the client opens each page in its own node tab without knowing
the source type.

## Catalog behavior

These four node kinds are leaves in the catalog. A click opens the node's
preferred representation, `[view, tree]`; the tab title is the node's name.
The old level that listed an Inspect row beside the tables is no longer
returned. Actions remain on the catalog row and keep their existing targets.

## Pages on the view

`DocumentView.pages` is a bounded list of source-issued pages. Each descriptor
has the child node id, a localized title and its ordered representations. The
client draws one button per descriptor and opens its first representation in
a separate tab named `<node> — <page>`. The view and its JSON were left to
switch in the same tab through `switchRepresentation`; D424 opens the JSON in a
tab of its own as well and removes the switch.

Docker declares Logs and Processes on a container, History on an image, and
Containers on a volume or network. Their child IDs remain valid for fetching
rows and for `path_to`; listing a Docker node as a catalog level returns no
children. A card opened from search or a link uses the node's own
representations, so it receives the same page list.

The page IDs preserve D414's watch behavior: Logs keeps its `follow=true`
stream, and a card remains a watched node that `views_told` refreshes on daemon
events while its connection catalog is open.

## Scope

The client has no Docker branches. Other sources may use `DocumentView.pages`
when a view should offer separate node tabs; a view with no pages keeps the
same behavior it has today.
