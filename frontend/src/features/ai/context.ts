import type { NodeRepresentation, ScreenContext } from "@/client"
import { connectionNameOf, lookOf } from "@/features/workspace/panels"
import type { Panel } from "@/features/workspace/panels"

const KIND_LABELS: Record<ScreenContext["kind"], string> = {
  catalog: "Catalog",
  rows: "Rows",
  content: "Content",
  structure: "Structure",
  summary: "Summary",
  record: "Record",
  chart: "Chart",
  queries: "Queries",
  query: "Query",
  result: "Result",
  relationships: "Relationships",
}

export interface AiOpenIntent {
  connector_id: string
  connector_name: string
  adapter_type: string
  node_id?: string | null
  title?: string | null
  view: "catalog" | "preferred" | "rows" | "structure" | "summary"
  describable: boolean
  representations: NodeRepresentation[]
}

function contextLabel(panel: Exclude<Panel, { kind: "connectors" | "widget" | "service-logs" | "search" }>): string {
  const look = lookOf(panel)
  const parts = [connectionNameOf(panel), look.title, KIND_LABELS[panel.kind]].filter(
    (part, index, all): part is string => Boolean(part) && all.indexOf(part) === index
  )
  return parts.join(" · ")
}

/**
 * Tabs whose content never reaches the model, so offering them invites the
 * model to pretend it saw them. An attached tab travels as one line of
 * identities — label, kind, connection, node — never its content, and no
 * tool reads a console's SQL or a captured result: `query` and `result` name
 * at most a connection the catalog already names better. A widget copy and a
 * service log have no kind the backend accepts (D133), so they stay off too.
 */
const UNATTACHABLE: ReadonlySet<ScreenContext["kind"]> = new Set([
  "query",
  "result",
])

/** Open workspace tabs which can be explicitly attached to one message. */
export function screenContexts(panels: readonly Panel[]): ScreenContext[] {
  return panels.flatMap((panel) => {
    // The Search tab names nothing of its own: what it found is opened from it.
    if (
      panel.kind === "connectors" ||
      panel.kind === "widget" ||
      panel.kind === "service-logs" ||
      panel.kind === "search"
    ) {
      return []
    }
    if (UNATTACHABLE.has(panel.kind)) return []
    const connectorId = "connectorId" in panel ? panel.connectorId : undefined
    const nodeId = "nodeId" in panel
      ? panel.nodeId
      : panel.kind === "chart"
        ? panel.request.node_id
        : undefined
    return [{
      panel_id: panel.id,
      label: contextLabel(panel),
      kind: panel.kind,
      ...(connectorId === undefined ? {} : { connector_id: connectorId }),
      ...(nodeId === undefined ? {} : { node_id: nodeId }),
    }]
  })
}
