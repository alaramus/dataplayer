/**
 * Drawing Mermaid diagrams, one at a time.
 *
 * Mermaid renders through one shared element of its own and re-reads global
 * configuration on every call, so two diagrams drawn at once take each other's
 * output: a document of four ended up with one diagram holding another's
 * contents and two holding nothing. Ids and a queue live in module scope —
 * inside `<script setup>` they would be per instance, which is the bug (D50).
 */

let identifiers = 0
let queue: Promise<unknown> = Promise.resolve()

export interface Diagram {
  svg: string
  /** The id Mermaid gave the root element, which scopes any added CSS to it. */
  id: string
}

/**
 * Correct what Mermaid draws once labels are native SVG text.
 *
 * Without HTML labels every edge label is given an opaque `rect.background`,
 * which reads as a box drawn around `yes` and `no` on a flowchart. A subgraph's
 * frame also comes out in Mermaid's own palette rather than this application's.
 * The rules are scoped by the diagram's id: a `<style>` inside inline SVG is a
 * stylesheet of the whole page.
 */
function corrections(id: string): string {
  return [
    `#${id} rect.background{display:none!important}`,
    `#${id} .edgeLabel rect{fill:none!important;stroke:none!important}`,
    `#${id} .cluster rect{fill:var(--dp-chrome-raised)!important;` +
      `stroke:var(--dp-border)!important;rx:8px;ry:8px}`,
  ].join("")
}

function withCorrections(svg: string, id: string): string {
  const css = corrections(id)
  return svg.includes("</style>")
    ? svg.replace("</style>", `${css}</style>`)
    : svg.replace("</svg>", `<style>${css}</style></svg>`)
}

/** Draw one diagram and return its SVG, after everything already queued. */
export async function renderDiagram(code: string, dark: boolean): Promise<Diagram> {
  // Loaded on first use: Mermaid is the largest thing a document can ask for,
  // and most documents never ask.
  const { default: mermaid } = await import("mermaid")

  const draw = async (): Promise<Diagram> => {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: dark ? "dark" : "default",
      // Mermaid writes node labels into a foreignObject of HTML unless told
      // otherwise, and foreignObject is forbidden for content nobody here
      // wrote. Native SVG text survives the sanitiser; HTML labels came back
      // as diagrams of empty shapes.
      htmlLabels: false,
      flowchart: { htmlLabels: false },
    })
    identifiers += 1
    const id = `markdown-mermaid-${String(identifiers)}`
    const { svg } = await mermaid.render(id, code)
    return { svg: withCorrections(svg, id), id }
  }

  const next = queue.then(draw, draw)
  queue = next.catch(() => undefined)
  return next
}
