import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { afterEach, describe, expect, it, vi } from "vitest"

import AppFullscreenToggle from "./AppFullscreenToggle.vue"

/**
 * jsdom implements no part of the Fullscreen API, so the browser's half is
 * played here: entering and leaving both announce themselves with the event
 * the component listens for, which is the only thing that tells it a user left
 * fullscreen with Escape.
 */
function fakeFullscreenApi() {
  let element: Element | null = null

  const request = vi.fn(async () => {
    element = document.documentElement
    document.dispatchEvent(new Event("fullscreenchange"))
  })
  const exit = vi.fn(async () => {
    element = null
    document.dispatchEvent(new Event("fullscreenchange"))
  })

  Object.defineProperty(document, "fullscreenElement", {
    configurable: true,
    get: () => element,
  })
  Object.defineProperty(document.documentElement, "requestFullscreen", {
    configurable: true,
    value: request,
  })
  Object.defineProperty(document, "exitFullscreen", { configurable: true, value: exit })

  return { request, exit }
}

const mountToggle = () => mount(AppFullscreenToggle, { global: { plugins: [Quasar] } })

const icon = (wrapper: ReturnType<typeof mountToggle>) => wrapper.get(".q-icon").text()

afterEach(() => {
  Reflect.deleteProperty(document, "fullscreenElement")
  Reflect.deleteProperty(document, "exitFullscreen")
  Reflect.deleteProperty(document.documentElement, "requestFullscreen")
})

describe("AppFullscreenToggle", () => {
  it("asks for the screen, then gives it back", async () => {
    const api = fakeFullscreenApi()
    const wrapper = mountToggle()

    expect(icon(wrapper)).toBe("fullscreen")

    await wrapper.get("button").trigger("click")
    await flushPromises()

    expect(api.request).toHaveBeenCalledTimes(1)
    expect(icon(wrapper)).toBe("fullscreen_exit")

    await wrapper.get("button").trigger("click")
    await flushPromises()

    expect(api.exit).toHaveBeenCalledTimes(1)
    expect(icon(wrapper)).toBe("fullscreen")
  })

  it("follows a fullscreen the button did not start, and an Escape out of it", async () => {
    fakeFullscreenApi()
    const wrapper = mountToggle()

    await document.documentElement.requestFullscreen()
    await flushPromises()
    expect(icon(wrapper)).toBe("fullscreen_exit")

    await document.exitFullscreen()
    await flushPromises()
    expect(icon(wrapper)).toBe("fullscreen")
  })

  it("is disabled where the browser has no fullscreen at all", () => {
    const wrapper = mountToggle()

    expect(wrapper.get("button").attributes("aria-disabled")).toBe("true")
  })
})
