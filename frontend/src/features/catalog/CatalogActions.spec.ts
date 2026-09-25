import { flushPromises, mount } from "@vue/test-utils"
import { AxiosError } from "axios"
import { computed, defineComponent } from "vue"
import type { Ref } from "vue"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { ActionInfo } from "@/client"
import type { MenuItem } from "@/shared/ui"
import CatalogActions from "./CatalogActions.vue"
import { clipboard, forgetClipboard, holdNodes } from "./clipboard"

const replies = vi.hoisted(() => new Map<string, ActionInfo[]>())
const offer = vi.hoisted(() => ({ available: false, reason: "Unavailable", name_conflict: false }))
const copyFile = vi.hoisted(() => vi.fn())
const moveFile = vi.hoisted(() => vi.fn())

vi.mock("@/client", () => ({
  ConnectorsService: { fileCopy: copyFile, fileMove: moveFile },
}))

vi.mock("@tanstack/vue-query", () => ({
  useQuery: () => ({
    data: computed(() => offer),
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
vi.mock("@/features/services/backups", () => ({
  useBackupSupport: () => computed(() => ({ offered: false })),
}))
vi.mock("@/shared/ui", () => ({
  AppIconButton: defineComponent({ template: "<button>Actions</button>" }),
  AppButton: defineComponent({ props: ["label"], template: "<button>{{ label }}</button>" }),
  AppMenu: defineComponent({ name: "AppMenu", props: ["items"], emits: ["select"], template: "<div />" }),
  useToast: () => ({ error: vi.fn(), success: vi.fn() }),
}))
vi.mock("@/shared/windows", () => ({
  WindowDialog: defineComponent({
    name: "WindowDialog",
    props: ["modelValue"],
    template: "<div><slot /><slot name='actions' /></div>",
  }),
}))
vi.mock("./ActionDialog.vue", () => ({
  default: defineComponent({
    name: "ActionDialog",
    props: ["command", "nodeIds", "nodeLabel", "targetNode"],
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

afterEach(() => {
  replies.clear()
  forgetClipboard()
  offer.available = false
  offer.reason = "Unavailable"
  offer.name_conflict = false
  copyFile.mockReset()
  moveFile.mockReset()
})

describe("catalog action subjects", () => {
  it("offers cross-connection Paste only when the pair is available", async () => {
    holdNodes("another", ["report.csv"], "copy")
    const wrapper = menu()
    const appMenu = wrapper.findComponent({ name: "AppMenu" })
    const item = () => (appMenu.props("items") as MenuItem[]).find((one) => one.name === "client:cross-paste")
    expect(item()?.disable).toBe(true)
    expect(item()?.hint).toBe("Unavailable")
    expect(item()?.label).toBe("Paste")
    wrapper.unmount()
    offer.available = true
    const enabled = menu()
    const enabledItem = (enabled.findComponent({ name: "AppMenu" }).props("items") as MenuItem[])
      .find((one) => one.name === "client:cross-paste")
    expect(enabledItem?.disable).toBe(false)
    enabled.unmount()
  })

  it("keeps the ordinary Paste label after copying in the same connection", () => {
    holdNodes("connection", ["report.csv"], "copy")
    const wrapper = menu([rename, load, paste])
    const items = wrapper.findComponent({ name: "AppMenu" }).props("items") as MenuItem[]
    expect(items.find((one) => one.name === "paste")?.label).toBe("Paste")
    wrapper.unmount()
  })

  it("keeps one Paste in the menu and opens conflict choices after selection", async () => {
    holdNodes("another", ["report.csv"], "copy")
    offer.name_conflict = true
    const wrapper = menu()
    const appMenu = wrapper.findComponent({ name: "AppMenu" })
    const items = appMenu.props("items") as MenuItem[]
    expect(items.filter((one) => one.name.startsWith("client:cross-paste"))).toHaveLength(1)
    expect(items.find((one) => one.name === "client:cross-paste")?.disable).toBe(false)
    appMenu.vm.$emit("select", "client:cross-paste")
    await flushPromises()
    expect(wrapper.findComponent({ name: "WindowDialog" }).exists()).toBe(true)
    expect(copyFile).not.toHaveBeenCalled()
    copyFile.mockResolvedValue({ data: { copied: 1, reload_node_ids: ["schema"] } })
    await wrapper.find('[data-testid="cross-paste-keep-both"]').trigger("click")
    await flushPromises()
    expect(copyFile).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({ conflict: "rename" }),
    }))
    wrapper.unmount()
  })

  it("reports a copied destination through the ordinary catalog reload path", async () => {
    holdNodes("another", ["report.csv"], "copy")
    offer.available = true
    copyFile.mockResolvedValue({ data: { copied: 1, reload_node_ids: ["schema"] } })
    const wrapper = menu()

    wrapper.findComponent({ name: "AppMenu" }).vm.$emit("select", "client:cross-paste")
    await flushPromises()

    expect(wrapper.emitted("done")?.[0]?.[0]).toMatchObject({
      done: [{ reload_node_ids: ["schema"] }],
    })
    wrapper.unmount()
  })

  it("moves a cut file and refreshes its source connection", async () => {
    holdNodes("another", ["report.csv"], "move")
    offer.available = true
    moveFile.mockResolvedValue({ data: { moved: 1, reload_node_ids: ["schema"] } })
    const wrapper = menu()

    wrapper.findComponent({ name: "AppMenu" }).vm.$emit("select", "client:cross-paste")
    await flushPromises()

    expect(moveFile).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({ conflict: "refuse" }),
    }))
    expect(wrapper.emitted("sourceChanged")?.[0]).toEqual(["another"])
    expect(wrapper.emitted("done")?.[0]?.[0]).toMatchObject({
      done: [{ reload_node_ids: ["schema"] }],
    })
    expect(clipboard.value).toBeNull()
    wrapper.unmount()
  })

  it("offers Keep both for a cut conflict without offering Replace", async () => {
    holdNodes("another", ["report.csv"], "move")
    offer.name_conflict = true
    const wrapper = menu()

    wrapper.findComponent({ name: "AppMenu" }).vm.$emit("select", "client:cross-paste")
    await flushPromises()

    expect(wrapper.find('[data-testid="cross-paste-keep-both"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cross-paste-replace"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("opens the same conflict window when a name is taken after the offer", async () => {
    holdNodes("another", ["report.csv"], "copy")
    offer.available = true
    copyFile.mockRejectedValueOnce(new AxiosError("refused", undefined, undefined, undefined, {
      status: 409,
    } as never))
    const wrapper = menu()

    wrapper.findComponent({ name: "AppMenu" }).vm.$emit("select", "client:cross-paste")
    await flushPromises()

    expect(copyFile).toHaveBeenCalledTimes(1)
    expect(wrapper.findComponent({ name: "WindowDialog" }).exists()).toBe(true)
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
