import { arrange } from "./layout"
import type { GraphDocument } from "./model"

self.onmessage = (event: MessageEvent<{ graph: GraphDocument; expanded: boolean }>) => {
  try {
    self.postMessage({ result: arrange(event.data.graph, event.data.expanded) })
  } catch {
    self.postMessage({ error: "This graph could not be arranged." })
  }
}
