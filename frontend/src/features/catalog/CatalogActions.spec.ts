/* eslint-disable vue/one-component-per-file -- stand-ins for the kit, a window and two dialogs, not components of the application. */
import { flushPromises, mount } from "@vue/test-utils"
import { computed, defineComponent } from "vue"
import type { Ref } from "vue"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { ActionInfo, ClipboardOffer, PasteOffer, TableOffer } from "@/client"
import type { MenuItem } from "@/shared/ui"
import CatalogActions from "./CatalogActions.vue"
import { clipboard, forgetClipboard, holdNodes } from "./clipboard"

const replies = vi.hoisted(() => new Map<string, ActionInfo[]>())
const answers = vi.hoisted(() => ({
  offers: [] as PasteOffer[],
  hold: undefined as ClipboardOffer | undefined,
  // Whether the source type says a table can be declared over it (D170).
  declares: false,
  table: undefined as TableOffer | undefined,
}))
const pasteCall = vi.hoisted(() => vi.fn())

vi.mock("@/client", () => ({
  ConnectorsService: { paste: pasteCall },
}))

// Two questions go to the server through this: what the clipboard can become
// here, and whether a selection here can be held at all.
vi.mock("@tanstack/vue-query", () => ({
  useQuery: (options: { queryKey: { value: unknown[] } }) => ({
    data: computed(() => {
      const asked = options.queryKey.value[0]
      if (asked === "paste-offers") return answers.offers
      if (asked === "table-offer") return answers.table
      return answers.hold
    }),
    isPending: computed(() => false),
    isError: computed(() => false),
  }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock("@/features/catalog/api", () => ({
  catalogKey: (connectorId: string, nodeId: string | null) => ["catalog", connectorId, nodeId],
  useNodeActions: (_connector: Ref<string>, ids: Ref<string[] | null>, enabled?: Ref<boolean>) => ({
    data: computed(() => enabled?.value === false ? undefined : replies.get(JSON.stringify(ids.value))),
  }),
  useDownloadAction: () => ({ mutateAsync: vi.fn() }),
  usePrepareConnectorAction: () => ({ isPending: computed(() => false), mutateAsync: vi.fn() }),
}))
vi.mock("@/features/connectors/api", () => ({
  useAdapterTypes: () => ({
    data: computed(() => answers.declares
      ? [{ name: "postgres", capabilities: [{ code: "declared_tables" }] }]
      : []),
  }),
}))
vi.mock("@/features/services/backups", () => ({
  useBackupSupport: () => computed(() => ({ offered: false })),
}))
vi.mock("@/shared/ui", () => ({
  AppIconButton: defineComponent({ template: "<button>Actions</button>" }),
  AppButton: defineComponent({ props: { label: { type: String, default: "" } }, template: "<button>{{ label }}</button>" }),
  AppMenu: defineComponent({ name: "AppMenu", props: { items: { type: Array, default: () => [] } }, emits: ["select"], template: "<div />" }),
  useToast: () => ({ error: vi.fn(), success: vi.fn() }),
}))
vi.mock("@/shared/windows", () => ({
  WindowDialog: defineComponent({
    name: "WindowDialog",
    props: { modelValue: Boolean },
    template: "<div><slot /><slot name='actions' /></div>",
  }),
}))
vi.mock("./CrossPaste.vue", () => ({
  default: defineComponent({
    name: "CrossPaste",
    props: { intent: { type: Object, default: null } },
    emits: ["done", "sourceChanged", "close"],
    template: "<div />",
  }),
}))
vi.mock("./DeclareTableWindow.vue", () => ({
  default: defineComponent({
    name: "DeclareTableWindow",
    props: {
      connectorId: { type: String, default: "" },
      nodeId: { type: String, default: "" },
      nodeLabel: { type: String, default: "" },
    },
    emits: ["done", "close"],
    template: "<div />",
  }),
}))
vi.mock("./ActionDialog.vue", () => ({
  default: defineComponent({
    name: "ActionDialog",
    props: {
      command: { type: Object, default: null },
      nodeIds: { type: Array, default: () => [] },
      nodeLabel: { type: String, default: "" },
      targetNode: { type: Object, default: null },
    },
    template: "<div />",
  }),
}))

const rename: ActionInfo = {
  name: "rename_schema", title: "Rename schema", acts_on: "group", offered_in: "catalog",
  applicable: true, destructive: false, takes_file: false, takes_many_files: false,
  previews: false, takes_set: false, previews_set: false, downloads: false,
  params_schema: { type: "object", properties: {} },
}
const load: ActionInfo = {
  ...rename, name: "load_csv", title: "Load from CSV", acts_on: "destination",
  takes_file: true, available_node_ids: ["schema", "other"],
  params_schema: { type: "object", "x-ui-workflow": "file-to-relation" },
}
const paste: ActionInfo = {
  ...rename,
  name: "paste",
  title: "Paste",
  acts_on: "children",
  params_schema: {
    type: "object",
    properties: {
      sources: {
        type: "array",
        items: { type: "string" },
        "x-ui-purpose": "clipboard-nodes",
        "x-ui-hidden": true,
      },
    },
  },
}

function menu(levelActions: ActionInfo[] = [rename, load]) {
  replies.set("null", levelActions)
  replies.set('["schema"]', [rename, paste])
  replies.set('["schema.table"]', [{ ...rename, applicable: false }])
  replies.set('["schema","other"]', [load])
  return mount(CatalogActions, {
    props: {
      connectorId: "connection", levelId: null, levelLabel: "Database", adapterType: "postgres",
      places: ["schema"], placeLabel: "Schema label",
      selectedGroups: [{ id: "schema", label: "Schema label", kind: "schema" }],
      groupings: [
        { id: "schema", label: "Schema label", system: false },
        { id: "other", label: "Other schema", system: false },
      ],
      checkedIds: ["schema.table"], checkedNodes: [{ label: "Table label", kind: "table" }],
      checkedLabel: "Table label", describesNodes: false, describedNode: null,
      drawsNodes: false, drawableNodes: false,
    },
  })
}

const copying: PasteOffer = { kind: "file_copy", title: "Copy files", available: true }

afterEach(() => {
  replies.clear()
  forgetClipboard()
  answers.offers = []
  answers.hold = undefined
  answers.declares = false
  answers.table = undefined
  pasteCall.mockReset()
})

function items(wrapper: ReturnType<typeof menu>) {
  return wrapper.findComponent({ name: "AppMenu" }).props("items") as MenuItem[]
}

describe("catalog action subjects", () => {
  it("describes the one ticked node as a table, where the source can have one (D170)", async () => {
    answers.declares = true
    answers.table = { available: true, reason: null, declared: false }
    const wrapper = menu()
    expect(items(wrapper).find((one) => one.name === "client:describe-table")?.disable).toBe(false)

    wrapper.findComponent({ name: "AppMenu" }).vm.$emit("select", "client:describe-table")
    await flushPromises()
    const window = wrapper.findComponent({ name: "DeclareTableWindow" })
    expect(window.props()).toEqual({
      connectorId: "connection", nodeId: "schema.table", nodeLabel: "Table label",
    })
    const outcome = { done: [{ message: "users declared", reload_node_ids: ["d0"] }], failures: [], total: 1 }
    window.vm.$emit("done", outcome)
    window.vm.$emit("close")
    await flushPromises()

    expect(wrapper.emitted("done")?.[0]).toEqual([outcome])
    expect(wrapper.findComponent({ name: "DeclareTableWindow" }).exists()).toBe(false)
    wrapper.unmount()
  })

  it("says why a selection cannot be described as a table, and draws nothing elsewhere", () => {
    answers.declares = true
    answers.table = { available: false, reason: "Select a folder to describe as a table" }
    const refused = menu()
    const line = items(refused).find((one) => one.name === "client:describe-table")
    expect(line?.disable).toBe(true)
    expect(line?.hint).toBe("Select a folder to describe as a table")
    refused.unmount()

    answers.declares = false
    const elsewhere = menu()
    expect(items(elsewhere).some((one) => one.name === "client:describe-table")).toBe(false)
    elsewhere.unmount()
  })

  it("offers cross-connection Paste only when an offer is usable", () => {
    holdNodes("another", ["report.csv"], "copy")
    answers.offers = [{ ...copying, available: false, reason: "Unavailable" }]
    const refused = menu()
    const item = items(refused).find((one) => one.name === "client:cross-paste")
    expect(item?.label).toBe("Paste")
    expect(item?.disable).toBe(true)
    expect(item?.hint).toBe("Unavailable")
    refused.unmount()

    answers.offers = [copying]
    const enabled = menu()
    expect(items(enabled).find((one) => one.name === "client:cross-paste")?.disable).toBe(false)
    enabled.unmount()
  })

  it("says so when nothing here can take what was copied", () => {
    holdNodes("another", ["public.people"], "copy")
    const wrapper = menu()

    const item = items(wrapper).find((one) => one.name === "client:cross-paste")

    expect(item?.disable).toBe(true)
    expect(item?.hint).toBe("Nothing here can take what was copied")
    wrapper.unmount()
  })

  it("keeps the ordinary Paste label after copying in the same connection", () => {
    holdNodes("connection", ["report.csv"], "copy")
    const wrapper = menu([rename, load, paste])
    expect(items(wrapper).find((one) => one.name === "paste")?.label).toBe("Paste")
    wrapper.unmount()
  })

  it("keeps one Paste and hands the chosen offer to the paste it starts", async () => {
    holdNodes("another", ["report.csv"], "move", "report.csv")
    answers.offers = [{ ...copying, kind: "file_move", name_conflict: true, available: false }]
    const wrapper = menu()
    expect(items(wrapper).filter((one) => one.name.startsWith("client:cross-paste"))).toHaveLength(1)

    wrapper.findComponent({ name: "AppMenu" }).vm.$emit("select", "client:cross-paste")
    await flushPromises()

    expect(wrapper.findComponent({ name: "CrossPaste" }).props("intent")).toEqual({
      sourceConnectorId: "another",
      sourceNodeIds: ["report.csv"],
      sourceLabel: "report.csv",
      mode: "move",
      destinationConnectorId: "connection",
      destinationNodeId: "schema",
      destinationLabel: "Schema label",
      targetNodeId: "schema.table",
      targetLabel: "Table label",
      offers: answers.offers,
    })
    // The menu starts it; the paste itself sends the request.
    expect(pasteCall).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it("passes on what the paste did and lets it go when it closes", async () => {
    holdNodes("another", ["report.csv"], "copy")
    answers.offers = [copying]
    const wrapper = menu()
    wrapper.findComponent({ name: "AppMenu" }).vm.$emit("select", "client:cross-paste")
    await flushPromises()
    const pasting = wrapper.findComponent({ name: "CrossPaste" })
    const outcome = { done: [{ message: "1 file copied", reload_node_ids: ["schema"] }], failures: [], total: 1 }

    pasting.vm.$emit("done", outcome)
    pasting.vm.$emit("sourceChanged", "another")
    pasting.vm.$emit("close")
    await flushPromises()

    expect(wrapper.emitted("done")?.[0]).toEqual([outcome])
    expect(wrapper.emitted("sourceChanged")?.[0]).toEqual(["another"])
    expect(wrapper.findComponent({ name: "CrossPaste" }).exists()).toBe(false)
    wrapper.unmount()
  })

  it("draws Copy without Cut where the server says a selection can only be copied", () => {
    answers.hold = { can_copy: { available: true }, can_cut: null }
    const wrapper = menu()

    const labels = items(wrapper).map((item) => item.label)

    expect(labels).toContain("Copy")
    expect(labels).not.toContain("Cut")
    expect(items(wrapper).find((item) => item.label === "Copy")?.disable).toBe(false)
    wrapper.unmount()
  })

  it("draws neither where nothing could take this source's nodes", () => {
    answers.hold = { can_copy: null, can_cut: null }
    const wrapper = menu()

    expect(items(wrapper).map((item) => item.label)).not.toContain("Copy")
    wrapper.unmount()
  })

  it("lets a source with its own Paste hold anything ticked", () => {
    const wrapper = menu([rename, load, paste])

    const held = items(wrapper).filter((item) => item.label === "Copy" || item.label === "Cut")

    expect(held.map((item) => item.disable)).toEqual([false, false])
    wrapper.unmount()
  })

  it("holds what is ticked under the name it is shown by", async () => {
    answers.hold = { can_copy: { available: true }, can_cut: null }
    const wrapper = menu()

    wrapper.findComponent({ name: "AppMenu" }).vm.$emit("select", "client:copy")
    await flushPromises()

    expect(clipboard.value).toEqual({
      connectorId: "connection",
      nodeIds: ["schema.table"],
      mode: "copy",
      label: "Table label",
    })
    // And lets the ticks go: left on, they made Paste aim at what was copied.
    expect(wrapper.emitted("untick")).toHaveLength(1)
    wrapper.unmount()
  })

  it("opens schema rename with the schema label and default while a table is checked", async () => {
    const wrapper = menu()
    const appMenu = wrapper.findComponent({ name: "AppMenu" })
    expect((appMenu.props("items") as MenuItem[]).find((item) => item.name === rename.name)?.disable).toBe(false)
    appMenu.vm.$emit("select", rename.name)
    await flushPromises()
    const dialog = wrapper.findComponent({ name: "ActionDialog" })
    expect(dialog.props("nodeIds")).toEqual(["schema"])
    expect(dialog.props("nodeLabel")).toBe("Schema label")
    expect(dialog.props("targetNode")).toMatchObject({ label: "Schema label", kind: "schema" })
    await wrapper.setProps({ selectedGroups: [], checkedIds: [], checkedNodes: [] })
    expect(dialog.props("nodeIds")).toEqual(["schema"])
    expect(dialog.props("nodeLabel")).toBe("Schema label")
    wrapper.unmount()
  })

  it("opens CSV creation once for one initial destination with multiple schemas displayed", async () => {
    const wrapper = menu()
    await wrapper.setProps({ places: ["schema", "other"], placeLabel: "Schema label, Other schema" })
    const appMenu = wrapper.findComponent({ name: "AppMenu" })
    expect((appMenu.props("items") as MenuItem[]).find((item) => item.name === load.name)?.disable).toBe(false)
    appMenu.vm.$emit("select", load.name)
    await flushPromises()
    const dialog = wrapper.findComponent({ name: "ActionDialog" })
    expect(dialog.props("nodeIds")).toEqual(["schema"])
    expect(dialog.props("nodeLabel")).toBe("Schema label")
    wrapper.unmount()
  })
})
