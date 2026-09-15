import type { NodeRepresentation, ScreenContext } from "@/client"
import { lookOf } from "@/features/workspace/panels"
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

/** Open workspace tabs which can be explicitly attached to one message. */
export function screenContexts(panels: readonly Panel[]): ScreenContext[] {
  return panels.flatMap((panel) => {
    if (panel.kind === "connectors") return []
    const connectorId = "connectorId" in panel ? panel.connectorId : undefined
    const nodeId = "nodeId" in panel
      ? panel.nodeId
      : panel.kind === "chart"
        ? panel.request.node_id
        : undefined
    return [{
      panel_id: panel.id,
      label: `${lookOf(panel).title} · ${KIND_LABELS[panel.kind]}`,
      kind: panel.kind,
      ...(connectorId === undefined ? {} : { connector_id: connectorId }),
      ...(nodeId === undefined ? {} : { node_id: nodeId }),
    }]
  })
}
