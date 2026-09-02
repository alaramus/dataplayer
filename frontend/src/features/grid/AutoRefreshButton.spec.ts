import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import { AppMenu } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

import AutoRefreshButton from "./AutoRefreshButton.vue"
import type { RefreshSeconds } from "./autoRefresh"

function mountButton(seconds: RefreshSeconds | null, held: string | null = null) {
  return mount(AutoRefreshButton, {
    props: { seconds, held },
    global: { plugins: [Quasar] },
  })
}

function buttonOf(wrapper: ReturnType<typeof mountButton>) {
  return wrapper.get('[data-testid="grid-auto-refresh"]')
}

function itemsOf(wrapper: ReturnType<typeof mountButton>): MenuItem[] {
  return wrapper.findComponent(AppMenu).props("items")
}

describe("the auto-refresh button", () => {
  it("says nothing but its icon while it is off", () => {
    const wrapper = mountButton(null)

    expect(buttonOf(wrapper).attributes("data-refresh")).toBe("off")
    expect(wrapper.text()).not.toContain("s")
  })

  it("wears the interval it is refreshing at", () => {
    const wrapper = mountButton(5)

    expect(buttonOf(wrapper).attributes("data-refresh")).toBe("5")
    expect(wrapper.text()).toContain("5 s")
  })

  it("ticks the interval that is on, and only that one", () => {
    const ticked = itemsOf(mountButton(30)).filter((item) => item.icon === "check")

    expect(ticked.map((item) => item.label)).toEqual(["30 s"])
  })

  it("ticks Off when nothing is on", () => {
    const ticked = itemsOf(mountButton(null)).filter((item) => item.icon === "check")

    expect(ticked.map((item) => item.label)).toEqual(["Off"])
  })

  it("reports the interval that was chosen", async () => {
    const wrapper = mountButton(null)

    wrapper.findComponent(AppMenu).vm.$emit("select", "s10")
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted("update:seconds")).toEqual([[10]])
  })

  it("reports being turned off", async () => {
    const wrapper = mountButton(10)

    wrapper.findComponent(AppMenu).vm.$emit("select", "off")
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted("update:seconds")).toEqual([[null]])
  })

  it("reports nothing for a name it does not know", async () => {
    const wrapper = mountButton(10)

    wrapper.findComponent(AppMenu).vm.$emit("select", "s7")
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted("update:seconds")).toBeUndefined()
  })
})
