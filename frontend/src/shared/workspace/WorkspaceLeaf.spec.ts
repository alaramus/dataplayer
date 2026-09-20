import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"
import { defineComponent, h, inject, ref } from "vue"
import type { PropType } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { makeLeaf } from "./model"
import type { LeafNode } from "./model"
import WorkspaceLeaf from "./WorkspaceLeaf.vue"
import WorkspacePanels from "./WorkspacePanels.vue"

/* eslint-disable vue/one-component-per-file -- two stand-ins for panel bodies, not components of the application. */
const Stub = defineComponent({ setup: () => () => h("div", { class: "stub" }, "panel body") })
const Hint = defineComponent({ setup: () => () => h("div", { class: "hint" }, "pick a source") })
const Rail = defineComponent({ setup: () => () => h("div", { class: "rail" }, "icons") })
const Head = defineComponent({ setup: () => () => h("div", { class: "head" }, "commands") })

const LeafWithPanels = defineComponent({
  props: { leaf: { type: Object as PropType<LeafNode>, required: true }, collapsible: Boolean },
  setup(props) {
    const context = inject(workspaceKey)
    if (context === undefined) throw new Error("Missing test workspace")
    return () => h(WorkspacePanels, { context }, () => h(WorkspaceLeaf, props))
  },
})

function contextFor(overrides: Partial<WorkspaceContext> = {}): WorkspaceContext {
  return {
    tree: ref(makeLeaf("a", ["p1", "p2"])),
    panelIds: ref(["p1", "p2"]),
    keyOf: (panelId) => panelId,
    detached: ref([]),
    focusedDetached: ref(null),
    focusedLeaf: ref(null),
    dragging: ref(null),
    lookOf: (panelId) => ({ title: `title ${panelId}`, icon: "square" }),
    componentOf: () => Stub,
    emptyOf: () => Hint,
    admissionOf: () => ({ accepts: true, remaining: 1 }),
    collapsedOf: () => null,
    headOf: () => null,
    sectionLookOf: () => ({ title: "Section", icon: "square" }),
    aside: ref([]),
    activate: () => undefined,
    canDetach: () => true,
    detach: () => undefined,
    dock: () => undefined,
    close: () => undefined,
    requestClose: async () => true,
    closeOthers: async () => undefined,
    focus: () => undefined,
    toggleCollapse: () => undefined,
    firstLeafId: ref(null),
    hideFirstCollapse: false,
    putAside: () => undefined,
    bringBack: () => undefined,
    resize: () => undefined,
    press: () => undefined,
    pointerMoved: () => undefined,
    endDrag: () => undefined,
    ...overrides,
  }
}

function mountLeaf(context: WorkspaceContext, collapsible = true, attached = false) {
  return mount(LeafWithPanels, {
    props: { leaf: makeLeaf("a", ["p1", "p2"]), collapsible },
    // Focus goes nowhere in a tree that is not in the document.
    ...(attached ? { attachTo: document.body } : {}),
    global: { plugins: [Quasar], provide: { [workspaceKey as symbol]: context } },
  })
}

describe("a section", () => {
  it("shows a tab per panel, titled by the feature", () => {
    const wrapper = mountLeaf(contextFor())
    expect(wrapper.get('[data-testid="workspace-tab-p1"]').text()).toContain("title p1")
    expect(wrapper.get('[data-testid="workspace-tab-p2"]').text()).toContain("title p2")
  })

  /**
   * U09: the tabs were a row of buttons. Nothing said they belonged together
   * or which of them was showing, and Tab walked through every one of them.
   */
  it("is a tab strip, and says which tab is showing", () => {
    const wrapper = mountLeaf(contextFor())
    const strip = wrapper.get('[role="tablist"]')
    const shown = wrapper.get('[data-testid="workspace-tab-p1"]')
    const other = wrapper.get('[data-testid="workspace-tab-p2"]')

    expect(strip.attributes("aria-label")).toBe("Open tabs")
    expect(shown.attributes("role")).toBe("tab")
    expect(shown.attributes("aria-selected")).toBe("true")
    expect(other.attributes("aria-selected")).toBe("false")
    // One tab stop for the strip, not one per tab.
    expect(shown.attributes("tabindex")).toBe("0")
    expect(other.attributes("tabindex")).toBe("-1")
  })

  it("walks the strip with the arrow keys without opening what it passes", async () => {
    const activated: string[] = []
    const wrapper = mountLeaf(contextFor({ activate: (id) => activated.push(id) }), true, true)
    const shown = wrapper.get('[data-testid="workspace-tab-p1"]')
    const other = wrapper.get('[data-testid="workspace-tab-p2"]')
    ;(shown.element as HTMLElement).focus()

    await wrapper.get('[role="tablist"]').trigger("keydown", { key: "ArrowRight" })
    expect(document.activeElement).toBe(other.element)

    await wrapper.get('[role="tablist"]').trigger("keydown", { key: "Home" })
    expect(document.activeElement).toBe(shown.element)

    // Walking is not choosing: a panel reads its rows when it is shown.
    expect(activated).toEqual([])
    await other.trigger("keydown", { key: "Enter" })
    expect(activated).toEqual(["p2"])
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

  it("renders only the active panel", async () => {
    const wrapper = mountLeaf(contextFor())
    await flushPromises()
    expect(wrapper.findAll(".stub")).toHaveLength(1)
  })

  it("activates the panel whose tab is clicked", async () => {
    const seen: string[] = []
    const wrapper = mountLeaf(contextFor({ activate: (id) => seen.push(id) }))
    await wrapper.get('[data-testid="workspace-tab-p2"]').trigger("click")
    expect(seen).toEqual(["p2"])
  })

  it("asks to close the panel whose cross is clicked", async () => {
    // Asks rather than closes: the panel may be holding something it has to
    // ask about first, and only the request path goes through that.
    const seen: string[] = []
    const wrapper = mountLeaf(
      contextFor({
        requestClose: async (id) => {
          seen.push(id)
          return true
        },
      })
    )
    await wrapper.get('[data-testid="workspace-close-p2"]').trigger("click")
    expect(seen).toEqual(["p2"])
  })

  it.each(["Enter", " "])("requests closing only the named tab with %s", async (key) => {
    const closed: string[] = []
    const activated: string[] = []
    const pressed: string[] = []
    const wrapper = mountLeaf(contextFor({
      requestClose: async (id) => { closed.push(id); return false },
      activate: (id) => activated.push(id),
      press: () => pressed.push("drag"),
    }))
    const close = wrapper.get('[data-testid="workspace-close-p2"]')
    expect(close.attributes("role")).toBe("button")
    expect(close.attributes("aria-label")).toBe("Close title p2")
    // The controls of a tab travel with it: p1 is the tab being shown, so its
    // close button is what Tab reaches, and p2's is reached by walking to p2
    // first (U09).
    expect(wrapper.get('[data-testid="workspace-close-p1"]').attributes("tabindex")).toBe("0")
    expect(close.attributes("tabindex")).toBe("-1")
    await close.trigger("pointerdown", { button: 0 })
    await close.trigger("keydown", { key })
    expect(closed).toEqual(["p2"])
    expect(activated).toEqual([])
    expect(pressed).toEqual([])
    expect(wrapper.find('[data-testid="workspace-tab-p2"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it.each(["Enter", " "])("activates a tab itself with %s", async (key) => {
    const activated: string[] = []
    const wrapper = mountLeaf(contextFor({ activate: (id) => activated.push(id) }))
    await wrapper.get('[data-testid="workspace-tab-p2"]').trigger("keydown", { key })
    expect(activated).toEqual(["p2"])
    wrapper.unmount()
  })

  it("opens the window when the icon of a catalog tab is clicked", async () => {
    const iconSeen: string[] = []
    const activated: string[] = []
    const wrapper = mountLeaf(
      contextFor({
        lookOf: (panelId) => ({
          title: `title ${panelId}`,
          icon: "square",
          iconTooltip: panelId === "p1" ? "Edit connection" : undefined,
          iconCommand: panelId === "p1",
        }),
        onIconClick: (id) => iconSeen.push(id),
        activate: (id) => activated.push(id),
      })
    )
    await wrapper.get('[data-testid="workspace-tab-icon-p1"]').trigger("click")
    expect(iconSeen).toEqual(["p1"])
    expect(activated).toEqual([])
  })

  // The tab is not where a panel is re-read any more: the button stands in the
  // panel's own row of commands, where a detached panel keeps it too (D112).
  it("draws no reload in the strip, whatever the look says", () => {
    const wrapper = mountLeaf(
      contextFor({
        lookOf: (panelId) => ({
          title: `title ${panelId}`,
          icon: "square",
          reloadTooltip: "Reload",
        }),
      })
    )
    expect(wrapper.find('[data-testid="workspace-reload-p1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="workspace-reload-p2"]').exists()).toBe(false)
  })

  // The defect this replaced: an icon was a button wherever it had a tooltip,
  // so four kinds offered a press with nothing behind it.
  it("leaves the icon inert when the look gives it a tooltip and no command", async () => {
    const iconSeen: string[] = []
    const activated: string[] = []
    const wrapper = mountLeaf(
      contextFor({
        lookOf: (panelId) => ({
          title: `title ${panelId}`,
          icon: "square",
          iconTooltip: "local pg",
        }),
        onIconClick: (id) => iconSeen.push(id),
        activate: (id) => activated.push(id),
      })
    )

    const icon = wrapper.get('[data-testid="workspace-tab-icon-p1"]')
    expect(icon.attributes("role")).toBeUndefined()
    await icon.trigger("click")

    expect(iconSeen).toEqual([])
    // The click reached the tab, which is what a click anywhere on a tab does.
    expect(activated).toEqual(["p1"])
  })

  it("shows no actionable icon when the handler is absent even though the look asks", () => {
    const wrapper = mountLeaf(
      contextFor({
        lookOf: () => ({
          title: "title p1",
          icon: "square",
          iconTooltip: "Edit connection",
          iconCommand: true,
        }),
      })
    )
    expect(wrapper.get('[data-testid="workspace-tab-icon-p1"]').attributes("role")).toBeUndefined()
  })

  it("does not activate the panel when its cross is clicked", async () => {
    // Without @click.stop the cross would bubble to the tab it sits in, so
    // closing a background panel would activate it on the way out.
    const activated: string[] = []
    const wrapper = mountLeaf(contextFor({ activate: (id) => activated.push(id) }))
    await wrapper.get('[data-testid="workspace-close-p2"]').trigger("click")
    expect(activated).toEqual([])
  })

  it("offers no handle at all when it is the only section", () => {
    const wrapper = mountLeaf(contextFor(), false)
    expect(wrapper.find('[data-testid="workspace-collapse-a"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="workspace-aside-a"]').exists()).toBe(false)
  })

  // Which of the two gestures a section offers follows from what the feature
  // would draw at forty pixels: something worth that width narrows to it, and
  // nothing worth it goes to the bar whole rather than leaving an empty strip.
  it("narrows a section whose panel has something to show at that width", async () => {
    const collapsed: string[] = []
    const wrapper = mountLeaf(
      contextFor({ collapsedOf: () => Rail, toggleCollapse: (id) => collapsed.push(id) })
    )
    expect(wrapper.find('[data-testid="workspace-aside-a"]').exists()).toBe(false)
    await wrapper.get('[data-testid="workspace-collapse-a"]').trigger("click")
    expect(collapsed).toEqual(["a"])
  })

  it("puts a section with nothing to show at that width on the bar", async () => {
    const asided: string[] = []
    const wrapper = mountLeaf(contextFor({ putAside: (id) => asided.push(id) }))
    expect(wrapper.find('[data-testid="workspace-collapse-a"]').exists()).toBe(false)
    await wrapper.get('[data-testid="workspace-aside-a"]').trigger("click")
    expect(asided).toEqual(["a"])
  })

  it("keeps a section on the screen while the feature cannot name it", () => {
    // Nothing could draw a way back to it, so it must not be able to leave.
    const wrapper = mountLeaf(contextFor({ sectionLookOf: () => null }))
    expect(wrapper.find('[data-testid="workspace-aside-a"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="workspace-collapse-a"]').exists()).toBe(true)
  })

  it("stands the first section's chevron down where the feature owns it", () => {
    // The application header collapses the first column; a second button for
    // the same gesture would only double it. Other sections keep theirs.
    const owned = mountLeaf(contextFor({
      collapsedOf: () => Rail,
      hideFirstCollapse: true,
      firstLeafId: ref("a"),
    }))
    expect(owned.find('[data-testid="workspace-collapse-a"]').exists()).toBe(false)
    const other = mountLeaf(contextFor({
      collapsedOf: () => Rail,
      hideFirstCollapse: true,
      firstLeafId: ref("elsewhere"),
    }))
    expect(other.find('[data-testid="workspace-collapse-a"]').exists()).toBe(true)
  })

  it("leaves only the rail standing under a collapsed first section", () => {
    const wrapper = mount(LeafWithPanels, {
      props: { leaf: { ...makeLeaf("a", ["p1"]), collapsed: true }, collapsible: true },
      global: {
        plugins: [Quasar],
        provide: {
          [workspaceKey as symbol]: contextFor({
            collapsedOf: () => Rail,
            hideFirstCollapse: true,
            firstLeafId: ref("a"),
          }),
        },
      },
    })
    expect(wrapper.findAll(".rail")).toHaveLength(1)
    expect(wrapper.find(".workspace-leaf__strip").exists()).toBe(false)
  })

  it("draws the feature's head instead of the tab of a panel alone in its section", async () => {
    const wrapper = mount(LeafWithPanels, {
      props: { leaf: makeLeaf("a", ["p1"]), collapsible: true },
      global: {
        plugins: [Quasar],
        provide: { [workspaceKey as symbol]: contextFor({ headOf: () => Head }) },
      },
    })
    // The body arrives a tick later, as in "renders only the active panel".
    await flushPromises()
    expect(wrapper.findAll(".head")).toHaveLength(1)
    expect(wrapper.find('[data-testid="workspace-tab-p1"]').exists()).toBe(false)
    expect(wrapper.findAll(".stub")).toHaveLength(1)
  })

  it("keeps the tabs while the section holds more than that panel", () => {
    const wrapper = mountLeaf(contextFor({ headOf: () => Head }))
    expect(wrapper.find(".head").exists()).toBe(false)
    expect(wrapper.find('[data-testid="workspace-tab-p1"]').exists()).toBe(true)
  })

  it("hides the body of a collapsed section but keeps the strip", () => {
    const wrapper = mount(LeafWithPanels, {
      props: { leaf: { ...makeLeaf("a", ["p1"]), collapsed: true }, collapsible: true },
      global: {
        plugins: [Quasar],
        provide: { [workspaceKey as symbol]: contextFor({ collapsedOf: () => Rail }) },
      },
    })
    expect(wrapper.findAll(".stub")).toHaveLength(0)
    expect(wrapper.find('[data-testid="workspace-collapse-a"]').exists()).toBe(true)
  })

  it("shows what the feature keeps at the width of a collapsed section", () => {
    const wrapper = mount(LeafWithPanels, {
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
    const wrapper = mountLeaf(contextFor({
        closeOthers: async (id) => {
          seen.push(id)
        },
      }))
    await wrapper.get('[data-testid="workspace-close-others-a"]').trigger("click")
    expect(seen).toEqual(["a"])
  })

  it("offers no such command when there is nothing else to close", () => {
    const wrapper = mount(LeafWithPanels, {
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
    const wrapper = mount(LeafWithPanels, {
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
    return mount(LeafWithPanels, {
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

  it("offers no handle, because a column saying what goes in it is all there is", () => {
    // Putting this aside would take the one line that says what could be
    // opened here off the screen and leave nothing in its place.
    const wrapper = mountEmpty()
    expect(wrapper.find('[data-testid="workspace-collapse-navigate"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="workspace-aside-navigate"]').exists()).toBe(false)
  })
})
