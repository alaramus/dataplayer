import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  AdaptersService,
  ConnectorsService,
  DeclaredReferencesService,
} from "@/client"
import type { RelationModel } from "@/client"
import DeclaredReferencesSection from "@/features/declared/DeclaredReferencesSection.vue"
import { AppInput, AppSelect, AppTooltip } from "@/shared/ui"
import { withWindowHost } from "@/shared/testing/windows"

import StructureView from "./StructureView.vue"

const MODEL: RelationModel = {
  node_id: "public.projects",
  schema_name: "public",
  name: "projects",
  kind: "table",
  owner: "postgres",
  persistence: "permanent",
  columns: [
    {
      position: 1,
      name: "name",
      type: { sql: "text", category: "string" },
      nullable: false,
      storage: "extended",
    },
    {
      position: 2,
      name: "note",
      type: { sql: "text", category: "string" },
      nullable: true,
      storage: "extended",
    },
  ],
  constraints: [
    {
      kind: "unique",
      name: "projects_name_key",
      columns: ["name"],
      nulls_not_distinct: false,
    },
  ],
  indexes: [
    {
      name: "projects_name_idx",
      method: "btree",
      columns: ["name"],
      definition: "CREATE INDEX projects_name_idx ON public.projects (name)",
    },
  ],
  column_changes_supported: true,
  index_changes_supported: true,
  constraint_changes_supported: true,
  candidate_keys: [{ name: "projects_name_key", columns: ["name"] }],
  index_methods: [
    {
      code: "btree",
      title: "B-tree",
      sql: "btree",
      unique_supported: true,
      multi_column_supported: true,
    },
    {
      code: "hash",
      title: "Hash",
      sql: "hash",
      unique_supported: false,
      multi_column_supported: false,
    },
  ],
  column_type_options: [
    { code: "text", title: "Text", sql: "text" },
    { code: "integer", title: "Integer", sql: "integer" },
  ],
}

function mountView() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(withWindowHost(StructureView, { connectorId: "connector-1", nodeId: "public.projects" }), {
    global: {
      plugins: [[Quasar, { plugins: { Dialog, Notify } }], [VueQueryPlugin, { queryClient }]],
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
  vi.spyOn(ConnectorsService, "readConnectors").mockResolvedValue({
    data: {
      data: [{ id: "connector-1", adapter_type: "postgres" }],
      count: 1,
    },
  } as never)
  vi.spyOn(AdaptersService, "readAdapterTypes").mockResolvedValue({
    data: [
      {
        name: "postgres",
        capabilities: [{ code: "declared_references" }],
      },
    ],
  } as never)
  vi.spyOn(ConnectorsService, "readRelationModel").mockResolvedValue({ data: MODEL } as never)
  // The constraint dialog asks the source where this relation lives and what
  // else lives there; without these it would reach for the network.
  vi.spyOn(ConnectorsService, "readNodePath").mockResolvedValue({
    data: [
      { id: "public", kind: "schema", name: "public" },
      { id: "public.projects", kind: "table", name: "projects" },
    ],
  } as never)
  vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
    data: [{ id: "public.people", kind: "table", name: "people" }],
  } as never)
  // The panel lists the references drawn from this node (D106); without this
  // the section beneath the indexes would reach for the network.
  vi.spyOn(DeclaredReferencesService, "referencesListDeclaredReferences").mockResolvedValue({
    data: [],
  } as never)
})

describe("structure capabilities and refusals", () => {
  it("shows declared references when the source has the capability", async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.findComponent(DeclaredReferencesSection).exists()).toBe(true)
  })

  it("does not offer declared references for Redis", async () => {
    vi.spyOn(ConnectorsService, "readConnectors").mockResolvedValue({
      data: {
        data: [{ id: "connector-1", adapter_type: "redis" }],
        count: 1,
      },
    } as never)
    vi.spyOn(AdaptersService, "readAdapterTypes").mockResolvedValue({
      data: [
        {
          name: "redis",
          capabilities: [{ code: "relation_model" }],
        },
      ],
    } as never)

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.findComponent(DeclaredReferencesSection).exists()).toBe(false)
  })

  it("renders read-only type and nullability as ordinary text with an explanation", async () => {
    vi.spyOn(ConnectorsService, "readRelationModel").mockResolvedValue({
      data: {
        ...MODEL,
        column_changes_supported: false,
        column_changes_reason: "This relation is read-only",
      },
    } as never)
    const wrapper = mountView()
    await flushPromises()
    for (const [id, value] of [
      ["structure-type-name", "text"],
      ["structure-nullability-name", "no"],
      ["structure-nullability-note", "yes"],
    ]) {
      const fact = wrapper.get(`[data-testid="${id}"]`)
      expect(fact.element.tagName).toBe("SPAN")
      expect(fact.text()).toBe(value)
      expect(fact.attributes("disabled")).toBeUndefined()
      expect(fact.findComponent(AppTooltip).exists()).toBe(true)
      await fact.trigger("click")
    }
    await flushPromises()
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
    wrapper.unmount()
  })

  it("gives the reason once rather than twice", async () => {
    vi.spyOn(ConnectorsService, "readRelationModel").mockResolvedValue({
      data: {
        ...MODEL,
        index_changes_supported: false,
        index_changes_reason: "A delimited file has no indexes",
      },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    const heading = wrapper
      .findAll(".structure-view__heading")
      .find((element) => element.text().includes("Indexes"))

    expect(heading).toBeDefined()
    // The kit's tooltip and nothing else. A `title` on the span beside it drew
    // the same sentence a second time, unstyled and over the first.
    expect(heading!.findComponent(AppTooltip).exists()).toBe(true)
    expect(heading!.findAll("[title]")).toHaveLength(0)
    wrapper.unmount()
  })
})

describe("relation column changes", () => {
  it("adds a column using a source-owned type code", async () => {
    const add = vi.spyOn(ConnectorsService, "addColumn").mockResolvedValue({
      data: { name: "review_note" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-add-column"]').trigger("click")
    await flushPromises()
    wrapper.findComponent(AppInput).vm.$emit("update:modelValue", "review_note")
    wrapper.findComponent(AppSelect).vm.$emit("update:modelValue", "text")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-add-save"]')?.click()
    await flushPromises()

    expect(add).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        name: "review_note",
        type_code: "text",
        nullable: true,
      },
    })
    wrapper.unmount()
  })

  it("drops the exact column only after confirmation", async () => {
    const drop = vi.spyOn(ConnectorsService, "dropColumn").mockResolvedValue({
      data: { name: "name" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-drop-name"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="confirm-accept"]')?.click()
    await flushPromises()

    expect(drop).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", name: "name" },
    })
    wrapper.unmount()
  })

  it("renames the exact column without a destructive confirmation", async () => {
    const rename = vi.spyOn(ConnectorsService, "renameColumn").mockResolvedValue({
      data: { name: "display_name" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-rename-name"]').trigger("click")
    await flushPromises()
    wrapper.findComponent(AppInput).vm.$emit("update:modelValue", "display_name")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-rename-save"]')?.click()
    await flushPromises()

    expect(rename).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", name: "name", new_name: "display_name" },
    })
    wrapper.unmount()
  })

  it("offers the one nullability change the column does not already have", async () => {
    const change = vi.spyOn(ConnectorsService, "changeColumnNullability").mockResolvedValue({
      data: { kind: "changed", name: "name", nullable: true },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-nullability-name"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-nullability-save"]')?.click()
    await flushPromises()

    expect(change).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", name: "name", nullable: true },
    })
    wrapper.unmount()
  })

  it("reads the count of rows in the way instead of treating it as a failure", async () => {
    vi.spyOn(ConnectorsService, "changeColumnNullability").mockResolvedValue({
      data: { kind: "blocked", name: "note", rows_without_value: 4, exact: true },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-nullability-note"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-nullability-save"]')?.click()
    await flushPromises()

    const blocked = document.body.querySelector('[data-testid="structure-nullability-blocked"]')
    expect(blocked?.textContent).toContain("4 rows have no value in note")
    // The dialog stays open, and nothing was reported as an error.
    expect(
      document.body.querySelector('[data-testid="structure-nullability-error"]')
    ).toBeNull()
    wrapper.unmount()
  })

  it("changes a type using a source-owned code and never a cast", async () => {
    const change = vi.spyOn(ConnectorsService, "changeColumnType").mockResolvedValue({
      data: { kind: "changed", name: "note", type_sql: "integer" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-type-note"]').trigger("click")
    await flushPromises()
    wrapper.findComponent(AppSelect).vm.$emit("update:modelValue", "integer")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-type-save"]')?.click()
    await flushPromises()

    // The opaque code from the source's own list, and nothing resembling a cast.
    expect(change).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", name: "note", type_code: "integer" },
    })
    wrapper.unmount()
  })

  it("reads the count of values the new type cannot take", async () => {
    vi.spyOn(ConnectorsService, "changeColumnType").mockResolvedValue({
      data: { kind: "blocked", name: "note", rows_not_convertible: 7, exact: false },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-type-note"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-type-save"]')?.click()
    await flushPromises()

    const blocked = document.body.querySelector('[data-testid="structure-type-blocked"]')
    expect(blocked?.textContent).toContain("More than 7 rows hold a value")
    expect(document.body.querySelector('[data-testid="structure-type-error"]')).toBeNull()
    wrapper.unmount()
  })

  it("creates an index without naming it", async () => {
    const create = vi.spyOn(ConnectorsService, "createIndex").mockResolvedValue({
      data: { kind: "created", name: "projects_note_idx" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-add-index"]').trigger("click")
    await flushPromises()
    wrapper.findComponent(AppSelect).vm.$emit("update:modelValue", ["note", "name"])
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-index-save"]')?.click()
    await flushPromises()

    // Columns in the order they were picked, a published method code, no name.
    expect(create).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        columns: ["note", "name"],
        method: "btree",
        unique: false,
      },
    })
    wrapper.unmount()
  })

  it("reads the count of values that already repeat", async () => {
    vi.spyOn(ConnectorsService, "createIndex").mockResolvedValue({
      data: { kind: "blocked", duplicate_groups: 3, exact: true },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-add-index"]').trigger("click")
    await flushPromises()
    wrapper.findComponent(AppSelect).vm.$emit("update:modelValue", ["name"])
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-index-save"]')?.click()
    await flushPromises()

    const blocked = document.body.querySelector('[data-testid="structure-index-blocked"]')
    expect(blocked?.textContent).toContain("3 values already appear more than once")
    expect(document.body.querySelector('[data-testid="structure-index-error"]')).toBeNull()
    wrapper.unmount()
  })

  it("drops an index the model named, after confirmation", async () => {
    const drop = vi.spyOn(ConnectorsService, "dropIndex").mockResolvedValue({
      data: { name: "projects_name_idx" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-drop-index-projects_name_idx"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="confirm-accept"]')?.click()
    await flushPromises()

    expect(drop).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", name: "projects_name_idx" },
    })
    wrapper.unmount()
  })

  it("adds a unique constraint without naming it", async () => {
    const create = vi.spyOn(ConnectorsService, "createConstraint").mockResolvedValue({
      data: { kind: "created", name: "projects_note_key" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-add-constraint"]').trigger("click")
    await flushPromises()
    // The second select in the dialog is the columns; the first is the kind.
    wrapper.findAllComponents(AppSelect)[1]?.vm.$emit("update:modelValue", ["note"])
    await flushPromises()
    document.body
      .querySelector<HTMLElement>('[data-testid="structure-constraint-save"]')
      ?.click()
    await flushPromises()

    expect(create).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        constraint: { kind: "unique", columns: ["note"] },
      },
    })
    wrapper.unmount()
  })

  it("reads the count of rows that point at nothing", async () => {
    vi.spyOn(ConnectorsService, "createConstraint").mockResolvedValue({
      data: { kind: "unmatched", rows: 5, exact: true },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-add-constraint"]').trigger("click")
    await flushPromises()
    wrapper.findAllComponents(AppSelect)[1]?.vm.$emit("update:modelValue", ["note"])
    await flushPromises()
    document.body
      .querySelector<HTMLElement>('[data-testid="structure-constraint-save"]')
      ?.click()
    await flushPromises()

    const blocked = document.body.querySelector(
      '[data-testid="structure-constraint-blocked"]'
    )
    expect(blocked?.textContent).toContain("5 rows point at nothing")
    wrapper.unmount()
  })

  it("drops a constraint the model named, after confirmation", async () => {
    const drop = vi.spyOn(ConnectorsService, "dropConstraint").mockResolvedValue({
      data: { name: "projects_name_key" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper
      .get('[data-testid="structure-drop-constraint-projects_name_key"]')
      .trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="confirm-accept"]')?.click()
    await flushPromises()

    expect(drop).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", name: "projects_name_key" },
    })
    wrapper.unmount()
  })

  it("sets an exact literal column default", async () => {
    const changeDefault = vi.spyOn(ConnectorsService, "changeColumnDefault").mockResolvedValue({
      data: { name: "name" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-default-name"]').trigger("click")
    await flushPromises()
    const input = document.body.querySelector<HTMLInputElement>(
      '[data-testid="structure-default-value"]'
    )
    if (input === null) throw new Error("default input did not open")
    input.value = "Robert'); DROP TABLE projects; --"
    input.dispatchEvent(new Event("input", { bubbles: true }))
    document.body.querySelector<HTMLElement>('[data-testid="structure-default-save"]')?.click()
    await flushPromises()

    expect(changeDefault).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        name: "name",
        action: "set",
        value: "Robert'); DROP TABLE projects; --",
      },
    })
    wrapper.unmount()
  })
})
