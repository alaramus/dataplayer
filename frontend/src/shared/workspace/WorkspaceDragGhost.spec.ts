import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import type { PanelLook } from "./context"
import WorkspaceDragGhost from "./WorkspaceDragGhost.vue"

const SAMPLE: PanelLook = { title: "orders", icon: "square", subtitle: "prod-db" }

function mountGhost(look: PanelLook = SAMPLE) {
  return mount(WorkspaceDragGhost, {
    props: { look, x: 120, y: 60 },
    global: { plugins: [Quasar] },
  })
}

describe("the tab in the hand", () => {
  it("says what the tab says", () => {
    const text = mountGhost().text()
    expect(text).toContain("orders")
    expect(text).toContain("prod-db")
  })

  it("says nothing more when the tab has no subtitle", () => {
    const wrapper = mountGhost({ title: "orders", icon: "square" })
    expect(wrapper.find(".drag-ghost__subtitle").exists()).toBe(false)
  })

  it("follows the pointer", () => {
    const style = mountGhost().get('[data-testid="workspace-drag-ghost"]').attributes("style")
    expect(style).toContain("left: 120px")
    expect(style).toContain("top: 60px")
  })
})
