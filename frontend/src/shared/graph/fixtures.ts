import type { GraphDocument } from "./model"

/** A non-relational producer keeps the viewer's extension contract concrete. */
export const deliveryGraph: GraphDocument = {
  groups: [{ id: "delivery", label: "Delivery" }, { id: "monitoring", label: "Monitoring" }],
  nodes: [
    { id: "api", label: "Gateway", groupId: "delivery", rows: [{ id: "events", label: "Events", detail: "stream" }, { id: "metrics", label: "Metrics" }] },
    { id: "worker", label: "Worker", groupId: "delivery", rows: [{ id: "input", label: "Input" }, { id: "retry", label: "Retry" }] },
    { id: "monitor", label: "Monitor", groupId: "monitoring", rows: [] },
  ],
  edges: [
    { id: "jobs", label: "Dispatch jobs", source: { nodeId: "api", portIds: ["events"] }, target: { nodeId: "worker", portIds: ["input"] }, directed: true },
    { id: "metrics", label: "Observe", source: { nodeId: "api", portIds: ["metrics"] }, target: { nodeId: "monitor" }, directed: false },
    { id: "retry", label: "Retry job", source: { nodeId: "worker", portIds: ["retry"] }, target: { nodeId: "worker", portIds: ["input"] }, directed: true },
  ],
}
