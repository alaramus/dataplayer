import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"
import { defineComponent, h, ref } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { makeLeaf } from "./model"
import WorkspaceLeaf from "./WorkspaceLeaf.vue"

/* eslint-disable vue/one-component-per-file -- two stand-ins for panel bodies, not components of the application. */
const Stub = defineComponent({ setup: () => () => h("div", { class: "stub" }, "panel body") })
const Hint = defineComponent({ setup: () => () => h("div", { class: "hint" }, "pick a source") })

function contextFor(overrides: Partial<WorkspaceContext> = {}): WorkspaceContext {
  return {
    tree: ref(makeLeaf("a", ["p1", "p2"])),
    focusedLeaf: ref(null),
    dragging: ref(null),
    lookOf: (panelId) => ({ title: `title ${panelId}`, icon: "square" }),
    componentOf: () => Stub,
    emptyOf: () => Hint,
    activate: () => undefined,
    close: () => undefined,
    focus: () => undefined,
    toggleCollapse: () => undefined,
    resize: () => undefined,
    startDrag: () => undefined,
    endDrag: () => undefined,
    ...overrides,
  }
}

function mountLeaf(context: WorkspaceContext, collapsible = true) {
  return mount(WorkspaceLeaf, {
    props: { leaf: makeLeaf("a", ["p1", "p2"]), collapsible },
    global: { plugins: [Quasar], provide: { [workspaceKey as symbol]: context } },
  })
}

describe("a section", () => {
  it("shows a tab per panel, titled by the feature", () => {
    const wrapper = mountLeaf(contextFor())
    expect(wrapper.get('[data-testid="workspace-tab-p1"]').text()).toContain("title p1")
    expect(wrapper.get('[data-testid="workspace-tab-p2"]').text()).toContain("title p2")
  })

  it("renders only the active panel", () => {
    expect(mountLeaf(contextFor()).findAll(".stub")).toHaveLength(1)
  })

  it("activates the panel whose tab is clicked", async () => {
    const seen: string[] = []
    const wrapper = mountLeaf(contextFor({ activate: (id) => seen.push(id) }))
    await wrapper.get('[data-testid="workspace-tab-p2"]').trigger("click")
    expect(seen).toEqual(["p2"])
  })

  it("closes the panel whose cross is clicked", async () => {
    const seen: string[] = []
    const wrapper = mountLeaf(contextFor({ close: (id) => seen.push(id) }))
    await wrapper.get('[data-testid="workspace-close-p2"]').trigger("click")
    expect(seen).toEqual(["p2"])
  })

  it("does not activate the panel when its cross is clicked", async () => {
    // Without @click.stop the cross would bubble to the tab it sits in, so
    // closing a background panel would activate it on the way out.
    const activated: string[] = []
    const wrapper = mountLeaf(contextFor({ activate: (id) => activated.push(id) }))
    await wrapper.get('[data-testid="workspace-close-p2"]').trigger("click")
    expect(activated).toEqual([])
  })

  it("offers no collapse handle when it is the only section", () => {
    const wrapper = mountLeaf(contextFor(), false)
    expect(wrapper.find('[data-testid="workspace-collapse-a"]').exists()).toBe(false)
  })

  it("hides the body of a collapsed section but keeps the strip", () => {
    const wrapper = mount(WorkspaceLeaf, {
      props: { leaf: { ...makeLeaf("a", ["p1"]), collapsed: true }, collapsible: true },
      global: { plugins: [Quasar], provide: { [workspaceKey as symbol]: contextFor() } },
    })
    expect(wrapper.findAll(".stub")).toHaveLength(0)
    expect(wrapper.find('[data-testid="workspace-collapse-a"]').exists()).toBe(true)
  })

  it("offers no cross on a panel the feature says cannot be closed", () => {
    const wrapper = mountLeaf(
      contextFor({
        lookOf: (panelId) => ({
          title: `title ${panelId}`,
          icon: "square",
          closable: panelId !== "p1",
        }),
      })
    )
    expect(wrapper.find('[data-testid="workspace-close-p1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="workspace-close-p2"]').exists()).toBe(true)
  })

  it("shows a drop overlay only while something is being dragged", async () => {
    const dragging = ref<string | null>(null)
    const wrapper = mountLeaf(contextFor({ dragging }))
    expect(wrapper.find('[data-testid="workspace-dropzone"]').exists()).toBe(false)
    dragging.value = "p1"
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="workspace-dropzone"]').exists()).toBe(true)
  })
})

/** A column of the screen that nothing has been opened in yet. See T2. */
describe("an empty pinned section", () => {
  function mountEmpty() {
    return mount(WorkspaceLeaf, {
      props: { leaf: makeLeaf("navigate", [], { pinned: true, accepts: "navigate" }), collapsible: true },
      global: { plugins: [Quasar], provide: { [workspaceKey as symbol]: contextFor() } },
    })
  }

  it("shows what the feature says belongs in it", () => {
    expect(mountEmpty().findAll(".hint")).toHaveLength(1)
  })

  it("shows no panel and no tab", () => {
    const wrapper = mountEmpty()
    expect(wrapper.findAll(".stub")).toHaveLength(0)
    expect(wrapper.findAll('[data-testid^="workspace-tab-"]')).toHaveLength(0)
  })

  it("keeps its collapse handle, so a column can still be pushed aside", () => {
    expect(mountEmpty().find('[data-testid="workspace-collapse-navigate"]').exists()).toBe(true)
  })
})
