# Markdown as a rendered document representation

## Problem

A `.md` file is currently classified as text, so its only representation is the
source editor. That is honest but poor: the whole point of Markdown is that it
is written as source and read as a document. Every reader of this repository
already works that way — the specs, the architecture files and this document
are Markdown.

The rendered form is also the first representation where the browser must build
DOM out of bytes that the platform did not author. Text, JSON and JSONL are
shown as characters; an image is shown by the browser's own decoder under
verified bounds. A rendered Markdown document is different in kind: it carries
raw HTML, links, images, and — in the documents this project actually
produces — diagrams and charts. A file can arrive from another user's
connection through a read grant (D33), so the author of the document is not
necessarily the person looking at it.

The previous slice settled that there is no generic preview mode: representation
order is the mechanism (D47), and editing stays its own capability (D48). This
slice is the first case where a node genuinely has two representations of the
same bytes — rendered and source.

## The viewer is ported, not invented

`C:\Users\maxim\PycharmProjects\rich-md-viewer` is a standalone Vue 3 + Quasar
application by the same author that renders exactly these documents. Its
rendering core is reused as an idea, on the same terms as every other port in
this repository: read it, then write the DataPlayer version. What is taken:

- fence-level block splitting, so a diagram or a chart never reaches the
  Markdown parser at all;
- two-stage sanitisation (below), which is the part that would be dangerous to
  reinvent;
- blocking remote resources by default;
- a per-block size ceiling and mounting heavy blocks only when they are seen.

What is left behind: its tabs, table of contents, in-document search, export,
share links, recent documents, service worker, five-language i18n and its
`highlight.js` code blocks. DataPlayer already owns tabs (workspace), files (the
file source), download (D49) and code highlighting (CodeMirror).

## Two representations of the same bytes

`.md` and `.markdown` become their own file format. `representations_of` returns
`[markdown, text]`: rendered first, source second. Nothing else changes about
the node — it is edited by D48's capability exactly as before, downloaded by
D49's action exactly as before, and it is not rows, so the row reader refuses it
the way it refuses an image.

`ContentRequest(representation="markdown")` returns `MarkdownContent`: the
document's text, and whether it was cut. The ceiling is 1 MB, between the 256 KB
text preview and the 4 MB editor: a rendered document is parsed, tokenised and
turned into DOM in the browser, which the other two are not. Above the ceiling
the rendered view states that it is showing the first megabyte, and the source
representation remains available up to its own limit.

Rendering happens entirely in the browser. The server sends the source text and
nothing else. No HTML crosses the API boundary, so there is no second place
where sanitisation could be forgotten, and a document is never stored rendered.

## Everything that becomes DOM is sanitised twice

The document is split at fence boundaries first. A `mermaid`, `echarts` or `svg`
fence becomes its own block and is never handed to the Markdown parser; a code
fence becomes a code block. What remains is Markdown prose, and it is rendered
by `markdown-it` with KaTeX and task lists.

Sanitisation happens at two levels, and the second one is not a duplicate of the
first:

1. **At token level.** `html_block` and `html_inline` renderer rules pass
   author-written raw HTML through DOMPurify with `style` forbidden. This runs
   before that HTML is combined with anything the renderer itself produced.
2. **Over the whole result.** The rendered string is sanitised again, this time
   keeping inline `style` only inside `.katex` — KaTeX positions fractions,
   matrices and indices with generated inline styles and is unreadable without
   them. Every `style` attribute outside a KaTeX subtree is dropped.

Then links and images are hardened. An `http(s)`, `mailto` or `tel` link is sent
to a new window with `rel="noopener noreferrer"` — a document is shown inside a
workspace panel, and a link followed in place would take the application with
it. A fragment stays as it is. Everything else, relative paths included, keeps
its text and loses its `href`: nothing resolves a path against the document's
own directory yet, and a link that navigates the workspace to a page that does
not exist is worse than a link that does nothing. Every image is
`loading="lazy"` and `referrerpolicy="no-referrer"`; inputs other than
checkboxes are removed and checkboxes are disabled. `iframe`, `object`, `embed`, `form` and `button` are
forbidden outright, so an embedded player is not a thing a document can ask for.

SVG — both a `svg` fence and Mermaid's output — goes through DOMPurify's SVG
profile with `script` and `foreignObject` forbidden. Mermaid additionally runs
with `securityLevel: "strict"`, so its own HTML labels never appear.

**Remote resources are blocked, and the block is visible.** An image whose
source is another origin is not fetched; its place says that a remote image was
blocked. This is the default because the document may be someone else's: a
remote image in a shared document is a read receipt for whoever hosts it, and
the reader did not ask to send one. Allowing them is a later, explicit choice
per document, not a setting that is set once and forgotten.

## Rich blocks are bounded and lazy

A single fence over 250 000 characters is not rendered; the block says it is too
large. Mermaid, ECharts, SVG and code blocks are asynchronous components mounted
by an `IntersectionObserver` when they scroll into view, so a document with
forty diagrams costs one diagram to open. Mermaid and KaTeX are loaded on first
use, not with the application.

Mermaid needs three things this design did not anticipate, all found by opening a
document with four diagrams in it. It renders through one shared element and
re-reads global configuration on every call, so concurrent renders take each
other's output — the shared id counter and a queue live in a module, not in a
component. It writes node labels into a `foreignObject` of HTML unless told
otherwise; that element is forbidden here, so the diagrams came back as empty
shapes until `htmlLabels` was turned off and labels became native SVG text. And
once labels are native text, every edge label is given an opaque background
rectangle, so `yes` and `no` on a flowchart appear boxed — CSS scoped to the
diagram's id hides it.

Charts need one correction of the same kind. A document names a chart's parts
and rarely their geometry, and ECharts places each part independently, so a
title and a legend both default to the top and overlap. The parts are laid out
in order — title, then legend, then the plot below both — filling in only what
the document left unsaid.

Code fences are rendered by the CodeMirror already used by the editor (D48),
read-only, resolving the language through the same `language.ts` used to
highlight the source. There is no second syntax highlighter in the bundle, and a
code block looks the same in the document as in the editor. Both take their
colours from one palette of theme tokens: CodeMirror's built-in style is a
light-theme palette, and it was putting dark purple keywords on a near-black
ground in the editor as well.

Every rich block wears the same frame — what it is on the left, what can be done
with it on the right. Its source can be copied, anything drawn as SVG can be
saved, and an `svg` fence can be read as its own source instead of its picture.
A reader should not have to learn a different corner for each kind of block, and
a document a colleague wrote is exactly the thing one wants to take a diagram
out of.

## An ECharts fence is document content, not a chart over a source

D35 says a chart is a closed view over one bounded fetch: line, bar or pie with
named fields, no raw ECharts option, no expression string. An `echarts` fence
carries a raw option object, so the two must be told apart deliberately.

They are different objects. D35 governs charts built **from a connection's
rows**, where a raw option or an expression would become an untyped query
language over the user's data. An `echarts` fence is **content of a document**,
in the same category as a Mermaid diagram: the author drew a picture, and the
picture's data was written into the file by hand. It reads nothing from any
connection, and it cannot name a relation, a column or a filter.

It is bounded anyway:

- the fence is parsed as JSON, so it cannot carry a function — a `formatter`
  callback is unrepresentable;
- it draws from one declared vocabulary, registered with the block and not with
  the application: line, bar, pie, scatter, radar, heatmap, gauge and funnel,
  with title, grid, legend, tooltip, zoom, toolbox and marks. This is wider than
  D35's, because a document already contains what it contains, while the chart
  panel composes an option out of what it offers to build;
- a series outside that vocabulary is named in the block rather than left as an
  empty box. ECharts reports an unregistered series to the console and draws
  nothing, which reads as a broken document, so the option is checked first;
- the fence is under the same character ceiling as every other rich block;
- rendering is the SVG renderer, into the component's own container.

This boundary is recorded as a known deviation next to D35: the vocabulary rule
holds for charts over data, and does not extend to pictures inside documents.

## A callout is a kind of block, not a kind of document

An agent writing a plan or a review marks its parts with fences named `summary`,
`decision`, `risk` and the like. Every other Markdown tool shows those as code
blocks, which is exactly why the convention is safe to adopt: nothing about the
document depends on this viewer. Here the kind is named with an icon and a
colour that carries the meaning, the leading `Key: value` lines are laid out as
fields, and the rest is rendered as Markdown through the same sanitised path as
any other prose. Nine kinds are drawn; anything else stays a code block.

## What this slice does not do

No table of contents, no in-document search, no export to HTML or PDF, no
YouTube or other embeds — a video is a fence this viewer leaves as code, because
`iframe` is forbidden for content the reader did not write — and no resolution
of relative image paths against the document's own directory — a relative image is
simply not fetched yet. Progressive rendering by token batches is not ported
either; the 1 MB ceiling is what bounds the work for now. Each of these is
separable and none of them changes the contract above.
