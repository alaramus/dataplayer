import { flushPromises, mount } from "@vue/test-utils"
import { computed, defineComponent } from "vue"
import type { Ref } from "vue"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { ActionInfo } from "@/client"
import type { MenuItem } from "@/shared/ui"
import CatalogActions from "./CatalogActions.vue"

const replies = vi.hoisted(() => new Map<string, ActionInfo[]>())

vi.mock("@/features/catalog/api", () => ({
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
  AppMenu: defineComponent({ name: "AppMenu", props: ["items"], emits: ["select"], template: "<div />" }),
  useToast: () => ({ error: vi.fn() }),
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

function menu() {
  replies.set("null", [rename, load])
  replies.set('["schema"]', [rename])
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

afterEach(() => { replies.clear() })

describe("catalog action subjects", () => {
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
