import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { ref } from "vue"
import { describe, expect, it } from "vitest"

import type { AsideSection, WorkspaceContext } from "./context"
import WorkspaceTaskbar from "./WorkspaceTaskbar.vue"

/**
 * The bar is the only way back to a section that is off the screen, so what it
 * is worth testing for is that it draws one entry per section and that
 * pressing one brings that section back.
 */
function contextFor(
  sections: AsideSection[],
  broughtBack: string[] = []
): WorkspaceContext {
  return {
    aside: ref(sections),
    bringBack: (id: string) => broughtBack.push(id),
  } as unknown as WorkspaceContext
}

const NAVIGATION: AsideSection = {
  id: "navigate",
  title: "Navigation",
  icon: "account_tree",
  panels: 2,
}

describe("the sections on the bar", () => {
  it("is not there at all while every section is on the screen", () => {
    const wrapper = mount(WorkspaceTaskbar, {
      global: { plugins: [Quasar] },
      props: { context: contextFor([]) },
    })

    expect(wrapper.find('[data-testid="workspace-taskbar"]').exists()).toBe(false)
  })

  it("names a section by its role and says how much is waiting in it", () => {
    const wrapper = mount(WorkspaceTaskbar, {
      global: { plugins: [Quasar] },
      props: { context: contextFor([NAVIGATION]) },
    })

    expect(wrapper.get('[data-testid="workspace-aside-navigate"]').text()).toContain(
      "Navigation · 2"
    )
  })

  it("brings one back when it is pressed", async () => {
    const broughtBack: string[] = []
    const wrapper = mount(WorkspaceTaskbar, {
      global: { plugins: [Quasar] },
      props: { context: contextFor([NAVIGATION], broughtBack) },
    })

    await wrapper.get('[data-testid="workspace-aside-navigate"]').trigger("click")

    expect(broughtBack).toEqual(["navigate"])
  })
})
