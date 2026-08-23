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
const Rail = defineComponent({ setup: () => () => h("div", { class: "rail" }, "icons") })

function contextFor(overrides: Partial<WorkspaceContext> = {}): WorkspaceContext {
  return {
    tree: ref(makeLeaf("a", ["p1", "p2"])),
    focusedLeaf: ref(null),
    dragging: ref(null),
    lookOf: (panelId) => ({ title: `title ${panelId}`, icon: "square" }),
    componentOf: () => Stub,
    emptyOf: () => Hint,
    admissionOf: () => ({ accepts: true, remaining: 1 }),
    collapsedOf: () => null,
    activate: () => undefined,
    close: () => undefined,
    closeOthers: () => undefined,
    focus: () => undefined,
    toggleCollapse: () => undefined,
    resize: () => undefined,
    press: () => undefined,
    pointerMoved: () => undefined,
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

  it("says quietly whose the panel is, when the feature says so", () => {
    // Two connections of one type are alike on the screen, and the name of the
    // node is what the eye looks for - so the subtitle stands beside it rather
    // than in front of it. See P8.
    const wrapper = mountLeaf(
      contextFor({
        lookOf: (panelId) => ({ title: `title ${panelId}`, icon: "square", subtitle: "prod-db" }),
      })
    )
    expect(wrapper.get('[data-testid="workspace-tab-p1"]').text()).toContain("prod-db")
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

  it("shows what the feature keeps at the width of a collapsed section", () => {
    const wrapper = mount(WorkspaceLeaf, {
      props: { leaf: { ...makeLeaf("a", ["p1"]), collapsed: true }, collapsible: true },
      global: {
        plugins: [Quasar],
        provide: { [workspaceKey as symbol]: contextFor({ collapsedOf: () => Rail }) },
      },
    })
    expect(wrapper.findAll(".rail")).toHaveLength(1)
    expect(wrapper.findAll(".stub")).toHaveLength(0)
  })

  it("closes every tab but the active one when asked", async () => {
    const seen: string[] = []
    const wrapper = mountLeaf(contextFor({ closeOthers: (id) => seen.push(id) }))
    await wrapper.get('[data-testid="workspace-close-others-a"]').trigger("click")
    expect(seen).toEqual(["a"])
  })

  it("offers no such command when there is nothing else to close", () => {
    const wrapper = mount(WorkspaceLeaf, {
      props: { leaf: makeLeaf("a", ["p1"]), collapsible: true },
      global: { plugins: [Quasar], provide: { [workspaceKey as symbol]: contextFor() } },
    })
    expect(wrapper.find('[data-testid="workspace-close-others-a"]').exists()).toBe(false)
  })

  it("offers no such command when the other tab has no cross of its own", () => {
    const wrapper = mountLeaf(
      contextFor({
        lookOf: (panelId) => ({
          title: `title ${panelId}`,
          icon: "square",
          closable: panelId !== "p2",
        }),
      })
    )
    expect(wrapper.find('[data-testid="workspace-close-others-a"]').exists()).toBe(false)
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

  it("marks where the panel would land when the section takes it", async () => {
    const wrapper = mountLeaf(contextFor({ dragging: ref<string | null>("p1") }))
    await wrapper.get('[data-testid="workspace-leaf-a"]').trigger("pointermove")
    expect(wrapper.get(".workspace-leaf__zone").attributes("style")).not.toContain("display: none")
  })

  it("does not draw the tab that is being dragged", async () => {
    // It is in the user's hand: leaving it in the strip as well is what made
    // the gesture hard to read at all. See G2.
    const wrapper = mountLeaf(contextFor({ dragging: ref<string | null>("p1") }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="workspace-tab-p1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="workspace-tab-p2"]').exists()).toBe(true)
  })

  it("marks the strip when the panel would join the tabs there", async () => {
    const wrapper = mountLeaf(contextFor({ dragging: ref<string | null>("p1") }))
    await wrapper.get('[data-testid="workspace-leaf-a"]').trigger("pointermove")
    expect(wrapper.get(".workspace-leaf__zone").classes()).toContain("workspace-leaf__zone--strip")
  })

  it("marks the whole of a section that holds nothing yet", async () => {
    const wrapper = mount(WorkspaceLeaf, {
      props: {
        leaf: makeLeaf("work", [], { pinned: true, accepts: "work" }),
        collapsible: true,
      },
      global: {
        plugins: [Quasar],
        provide: {
          [workspaceKey as symbol]: contextFor({ dragging: ref<string | null>("p1") }),
        },
      },
    })
    await wrapper.get('[data-testid="workspace-leaf-work"]').trigger("pointermove")
    expect(wrapper.get(".workspace-leaf__zone").classes()).toContain("workspace-leaf__zone--whole")
  })

  it("marks nothing at all in a section that refuses it", async () => {
    // A refusal has to be visible before the button is released, and the only
    // way this screen says it is by not promising anything. See P1.
    const wrapper = mountLeaf(
      contextFor({
        dragging: ref<string | null>("p1"),
        admissionOf: () => ({ accepts: false, remaining: 1 }),
      })
    )
    await wrapper.get('[data-testid="workspace-leaf-a"]').trigger("pointermove")
    expect(wrapper.get(".workspace-leaf__zone").attributes("style")).toContain("display: none")
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
