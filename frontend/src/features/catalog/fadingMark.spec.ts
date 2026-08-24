import { effectScope } from "vue"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useFadingMark } from "@/features/catalog/fadingMark"

/**
 * A mark that takes itself off.
 *
 * In an effect scope rather than a mounted component: the composable only
 * needs a scope to be cleaned up by, and a scope is something a test can open
 * and close by hand.
 */
function inScope<T>(run: () => T): { result: T; dispose: () => void } {
  const scope = effectScope()
  const result = scope.run(run)
  if (result === undefined) throw new Error("the scope did not run")
  return { result, dispose: () => scope.stop() }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("a mark that fades", () => {
  it("shows what it was given, at once", () => {
    const { result: mark, dispose } = inScope(() => useFadingMark(3000))

    mark.show("public.orders")

    expect(mark.value.value).toBe("public.orders")
    dispose()
  })

  it("takes it off once the time is up", () => {
    const { result: mark, dispose } = inScope(() => useFadingMark(3000))
    mark.show("public.orders")

    vi.advanceTimersByTime(3000)

    expect(mark.value.value).toBeNull()
    dispose()
  })

  it("is still showing just before the time is up", () => {
    const { result: mark, dispose } = inScope(() => useFadingMark(3000))
    mark.show("public.orders")

    vi.advanceTimersByTime(2999)

    expect(mark.value.value).toBe("public.orders")
    dispose()
  })

  // Being pointed at a second row starts the few seconds again. Otherwise the
  // second mark inherits whatever was left of the first one's time.
  it("starts the clock again when something else is shown", () => {
    const { result: mark, dispose } = inScope(() => useFadingMark(3000))
    mark.show("public.orders")
    vi.advanceTimersByTime(2000)

    mark.show("public.users")
    vi.advanceTimersByTime(2000)

    expect(mark.value.value).toBe("public.users")
    dispose()
  })

  it("takes it off when asked, without waiting", () => {
    const { result: mark, dispose } = inScope(() => useFadingMark(3000))
    mark.show("public.orders")

    mark.clear()

    expect(mark.value.value).toBeNull()
    dispose()
  })

  // A timer that outlives the panel would write into a ref nobody reads, and
  // in a test it is the thing that keeps the run open.
  it("drops its timer when the scope goes", () => {
    const { result: mark, dispose } = inScope(() => useFadingMark(3000))
    mark.show("public.orders")

    dispose()
    vi.advanceTimersByTime(3000)

    expect(vi.getTimerCount()).toBe(0)
  })
})
