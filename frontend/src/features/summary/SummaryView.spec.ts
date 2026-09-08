import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { ref } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { NodeSummary, RelatedView } from "@/client"
import SummaryPanel from "@/features/workspace/panels/SummaryPanel.vue"
import { workspaceActionsKey } from "@/features/workspace/state"

const data = ref<NodeSummary>()
const followReference = vi.fn()
vi.mock("@/features/summary/api", () => ({
  useNodeSummary: () => ({ data, error: ref(null), isPending: ref(false), refetch: vi.fn() }),
}))
vi.mock("@/features/workspace/reloadable", () => ({ useReloadable: vi.fn() }))

const related: RelatedView = {
  node: {
    id: "pg_dataplayer.timescale.v1.chunks", name: "Chunks", kind: "report",
    has_children: false, describable: false,
    representations: [{ kind: "table", title: "View as table" }],
  },
  filters: [
    { column: "hypertable_schema", op: "eq", value: "odd.schema" },
    { column: "hypertable_name", op: "eq", value: "table'name" },
  ],
}

function panel() {
  return mount(SummaryPanel, {
    props: {
      panelId: "details", connectorId: "connector", nodeId: "logical-node",
      title: "Metrics", connectorName: "Source", adapterType: "postgres",
    },
    global: {
      plugins: [Quasar],
      provide: { [workspaceActionsKey as symbol]: { followReference } },
      stubs: { PanelCommands: true },
    },
  })
}

beforeEach(() => {
  followReference.mockReset()
  data.value = {
    node_id: "logical-node", name: "Metrics", kind: "table",
    contents: {
      kind: "relation", relation_kind: "table", schema_name: "odd.schema",
      specialization: { kind: "timescale_hypertable" },
      columns: 2, indexes: 1, constraints: 1,
    },
    related_views: [related],
  }
})

describe("Details report navigation", () => {
  it("renders exact chunk counts and configuration without claiming all chunks are compressed", () => {
    if (data.value?.contents?.kind !== "relation") throw new Error("The relation is missing")
    data.value.contents.timescale = {
      kind: "hypertable", num_dimensions: 2, num_chunks: "9007199254740993",
      compression_enabled: false,
    }
    const wrapper = panel()
    expect(wrapper.get('[data-testid="summary-fact-Chunks"]').text()).toBe("9007199254740993")
    expect(wrapper.get('[data-testid="summary-fact-Dimensions"]').text()).toBe("2")
    expect(wrapper.get('[data-testid="summary-fact-Compression configured"]').text()).toBe("No")
  })

  it("retains basic facts and report navigation when optional inspection fails", async () => {
    if (data.value?.contents?.kind !== "relation") throw new Error("The relation is missing")
    data.value.contents.timescale = {
      kind: "unavailable", reason: "TimescaleDB metadata inspection timed out",
    }
    const wrapper = panel()
    expect(wrapper.text()).toContain("TimescaleDB metadata inspection timed out")
    expect(wrapper.get('[data-testid="summary-fact-Columns"]').text()).toBe("2")
    const button = wrapper.findAll("button").find((button) => button.text() === "Chunks")
    if (button === undefined) throw new Error("The Chunks link is missing")
    await button.trigger("click")
    expect(followReference).toHaveBeenCalledOnce()
  })

  it("shows specialization and forwards the source node and editable filters", async () => {
    const wrapper = panel()
    expect(wrapper.text()).toContain("TimescaleDB hypertable")
    const button = wrapper.findAll("button").find((button) => button.text() === "Chunks")
    expect(button).toBeDefined()
    if (button === undefined) throw new Error("The Chunks link is missing")
    await button.trigger("click")
    expect(followReference).toHaveBeenCalledWith({
      connectorId: "connector", connectorName: "Source", adapterType: "postgres",
      target: { kind: "rows", node: related.node, filters: related.filters },
    })
  })

  it("keeps older summaries usable when related views and specialization are absent", () => {
    data.value = { node_id: "notes", name: "Notes", kind: "file" }
    const wrapper = panel()
    expect(wrapper.find('[data-testid="summary-related-views"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain("TimescaleDB")
  })

  it("describes continuous aggregates without presenting them as hypertables", () => {
    if (data.value === undefined) throw new Error("The summary is missing")
    data.value.contents = {
      kind: "relation", relation_kind: "view", schema_name: "public",
      specialization: { kind: "timescale_continuous_aggregate" },
      columns: 2, indexes: 0, constraints: 0,
      timescale: {
        kind: "continuous_aggregate", hypertable_schema: "source",
        hypertable_name: "metrics", materialization_hypertable_schema: "internal",
        materialization_hypertable_name: "materialized", materialized_only: false,
        compression_enabled: true,
      },
    }
    const wrapper = panel()
    expect(wrapper.text()).toContain("TimescaleDB continuous aggregate")
    expect(wrapper.get('[data-testid="summary-fact-Source hypertable"]').text()).toBe("metrics")
    expect(wrapper.get('[data-testid="summary-fact-Materialized only"]').text()).toBe("No")
  })
})
