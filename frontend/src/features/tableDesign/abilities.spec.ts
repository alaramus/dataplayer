import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { afterEach, describe, expect, it } from "vitest"
import { computed, reactive } from "vue"

import type { DesignAbilities, EngineOption, TableDesignOptions } from "@/client"

import ConstraintInspector from "./ConstraintInspector.vue"
import DesignNavigation from "./DesignNavigation.vue"
import { forgetDesign, registerDesign } from "./design"
import { emptyDraft, newIndex } from "./draft"
import IndexInspector from "./IndexInspector.vue"
import TableOptionsInspector from "./TableOptionsInspector.vue"

const ID = "abilities-test"

const EVERYTHING: DesignAbilities = {
  unique_constraints: true,
  foreign_keys: true,
  deferrable_unique: true,
  deferrable_foreign_keys: true,
  index_direction: true,
  index_nulls_order: true,
  index_include: true,
  partial_indexes: true,
  comments: true,
  tablespaces: true,
}

/** A draft with one index, registered with what a source said it has. */
function design(abilities: DesignAbilities, options: Partial<TableDesignOptions> = {}) {
  const draft = reactive(emptyDraft("text"))
  const index = newIndex("btree", draft.columns[0]!.id)
  draft.indexes.push(index)
  registerDesign(ID, {
    draft,
    options: computed(() => ({ abilities, ...options })),
    abilities: computed(() => abilities),
    engine: computed(() => options.engines?.[0] ?? null),
    sorted: computed(() => options.engines?.[0]?.sorted !== false),
    columnChoices: computed(() => draft.columns.map((column) => ({ label: column.name, value: column.id }))),
    typeChoices: computed(() => []),
    types: computed(() => []),
    functions: computed(() => []),
    databases: computed(() => false),
  })
  return { draft, indexId: index.id }
}

const plugins = { global: { plugins: [Quasar] } }

afterEach(() => forgetDesign(ID))

describe("a designer shows only what the source has", () => {
  it("leaves out foreign keys and an empty storage page for a ClickHouse-like source", () => {
    design({ comments: true }, { hypertable: { offered: false } })
    const wrapper = mount(DesignNavigation, {
      ...plugins,
      props: { designId: ID, section: "columns", selected: "", problems: [] },
    })

    expect(wrapper.find('[data-testid="section-foreign-keys"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="section-options"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="section-indexes"]').exists()).toBe(true)
  })

  it("keeps every section where the source has all of it", () => {
    design(EVERYTHING, { partition_strategies: [{ code: "range", title: "Range" }] })
    const wrapper = mount(DesignNavigation, {
      ...plugins,
      props: { designId: ID, section: "columns", selected: "", problems: [] },
    })

    expect(wrapper.find('[data-testid="section-foreign-keys"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="object-options"]').exists()).toBe(true)
  })

  it("offers no unique constraint where the source has none", () => {
    design({ comments: true })
    const wrapper = mount(ConstraintInspector, { ...plugins, props: { designId: ID } })

    expect(wrapper.find('[data-testid="add-unique"]').exists()).toBe(false)
  })

  it("draws an index without order, nulls or a predicate the source cannot keep", () => {
    const { indexId } = design({ comments: true })
    const wrapper = mount(IndexInspector, { ...plugins, props: { designId: ID, indexId } })

    expect(wrapper.text()).not.toContain("NULL")
    expect(wrapper.find('[data-testid="index-predicate-field"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="index-key-column-0"]').exists()).toBe(true)
  })

  it("draws the whole index where the source has every part", () => {
    const { indexId } = design(EVERYTHING)
    const wrapper = mount(IndexInspector, { ...plugins, props: { designId: ID, indexId } })

    expect(wrapper.find('[data-testid="index-predicate-field"]').exists()).toBe(true)
  })

  it("offers the engines a source keeps tables by, and the columns each takes", () => {
    const engines: EngineOption[] = [
      { code: "MergeTree", title: "MergeTree", description: "The usual choice" },
      {
        code: "CollapsingMergeTree",
        title: "CollapsingMergeTree",
        merges_by_key: true,
        parameters: [{ code: "sign", title: "Sign column", required: true, type_codes: ["text"] }],
      },
    ]
    design({ comments: true }, { engines })
    const navigation = mount(DesignNavigation, {
      ...plugins,
      props: { designId: ID, section: "columns", selected: "", problems: [] },
    })
    const options = mount(TableOptionsInspector, { ...plugins, props: { designId: ID } })

    expect(navigation.find('[data-testid="object-options"]').exists()).toBe(true)
    expect(options.find('[data-testid="table-engine"]').exists()).toBe(true)
    expect(options.text()).toContain("The usual choice")
  })

  it("leaves indexes out under an engine that keeps rows as they arrive", () => {
    const { draft } = design(
      { comments: true },
      { engines: [{ code: "Log", title: "Log", sorted: false }, { code: "MergeTree", title: "MergeTree" }] }
    )
    draft.indexes.splice(0)
    const wrapper = mount(DesignNavigation, {
      ...plugins,
      props: { designId: ID, section: "columns", selected: "", problems: [] },
    })

    expect(wrapper.find('[data-testid="section-indexes"]').exists()).toBe(false)
  })
})
