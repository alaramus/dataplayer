import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import FreshnessBadge from "./FreshnessBadge.vue"
import { freshnessOf } from "./freshness"

function mountBadge(
  headers: Record<string, unknown> | undefined,
  cacheTtlSeconds: number | null = null,
  agedBy = 0
) {
  return mount(FreshnessBadge, {
    props: {
      freshness:
        headers === undefined ? undefined : freshnessOf(headers, Date.now() - agedBy),
      cacheTtlSeconds,
    },
    global: { plugins: [Quasar] },
  })
}

function badgeOf(wrapper: ReturnType<typeof mountBadge>) {
  return wrapper.get('[data-testid="freshness"]')
}

describe("which badge a test is looking at", () => {
  it("answers to the name it was given, and to a plain one otherwise", () => {
    // Two are on screen at once - a catalog level and the rows opened out of
    // it - and a test that could not tell them apart would assert about
    // whichever rendered first.
    const plain = mountBadge({ "x-data-cache": "miss" })
    expect(plain.find('[data-testid="freshness"]').exists()).toBe(true)
    const named = mount(FreshnessBadge, {
      props: {
        freshness: freshnessOf({ "x-data-cache": "miss" }),
        testid: "grid-freshness",
      },
      global: { plugins: [Quasar] },
    })
    expect(named.find('[data-testid="grid-freshness"]').exists()).toBe(true)
  })
})

describe("the freshness badge", () => {
  it("says a page read from the source is live", () => {
    const wrapper = mountBadge({ "x-data-cache": "miss" })

    expect(badgeOf(wrapper).attributes("data-live")).toBe("yes")
    expect(wrapper.text()).toContain("Live")
  })

  it("says how old a kept answer is instead", () => {
    const wrapper = mountBadge({
      "x-data-cache": "hit",
      "x-data-cache-age": "20",
    })

    expect(badgeOf(wrapper).attributes("data-live")).toBe("no")
    expect(wrapper.text()).toContain("20s")
  })

  it("stops calling a page live once it has aged on screen", () => {
    // The reply said it was a read of the source. Four minutes later that is
    // still true and no longer the point.
    const wrapper = mountBadge({ "x-data-cache": "miss" }, null, 240_000)

    expect(badgeOf(wrapper).attributes("data-live")).toBe("no")
    expect(wrapper.text()).toContain("4m")
  })

  it("is not drawn at all before anything has been read", () => {
    expect(mountBadge(undefined).find('[data-testid="freshness"]').exists()).toBe(
      false
    )
  })

  it("asks for a reload when pressed", async () => {
    const wrapper = mountBadge({ "x-data-cache": "hit", "x-data-cache-age": "5" })

    await badgeOf(wrapper).trigger("click")

    expect(wrapper.emitted("reload")).toHaveLength(1)
  })
})
