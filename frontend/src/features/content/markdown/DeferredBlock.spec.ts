import { mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"

import DeferredBlock from "./DeferredBlock.vue"

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("a deferred document block", () => {
  it("mounts immediately when a complete export asks for it", async () => {
    const disconnectSpy = vi.fn()
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        disconnect = disconnectSpy
        observe() {}
        unobserve() {}
        takeRecords() {
          return []
        }
        readonly root = null
        readonly rootMargin = "0px"
        readonly thresholds = []
      }
    )

    const wrapper = mount(DeferredBlock, {
      props: { eager: false },
      slots: { default: '<div data-testid="drawn">drawn</div>' },
    })
    expect(wrapper.find('[data-testid="drawn"]').exists()).toBe(false)

    await wrapper.setProps({ eager: true })

    expect(wrapper.get('[data-testid="drawn"]').text()).toBe("drawn")
    expect(disconnectSpy).toHaveBeenCalled()
  })
})
