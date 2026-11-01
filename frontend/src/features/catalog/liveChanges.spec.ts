import { effectScope, nextTick, ref } from "vue"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"

import { CHANGES_TOPIC, useLiveChanges } from "./liveChanges"
import type { SourceChangesEvent } from "./liveChanges"

const listeners = new Map<string, (payload: unknown) => void>()
const stopListening = vi.fn()
const subscribe = vi.fn((topic: string, listener: (payload: unknown) => void) => {
  listeners.set(topic, listener)
  return stopListening
})

vi.mock("@/shared/realtime/client", () => ({ realtime: () => ({ subscribe }) }))

let follow: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.useFakeTimers()
  listeners.clear()
  subscribe.mockClear()
  stopListening.mockClear()
  follow = vi.fn().mockResolvedValue({})
  vi.spyOn(ConnectorsService, "followChanges").mockImplementation(follow as never)
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function asked(): { connector: string; nodes: (string | null)[] }[] {
  return follow.mock.calls.map(([options]: unknown[]) => {
    const { path, body } = options as { path: { connector_id: string }; body: { node_ids: (string | null)[] } }
    return { connector: path.connector_id, nodes: body.node_ids }
  })
}

function setUp(live = true) {
  const connectorId = ref("c1")
  const isLive = ref(live)
  const shown = ref<(string | null)[]>([null, "/app"])
  const onChange = vi.fn()
  const scope = effectScope()
  scope.run(() =>
    useLiveChanges({
      connectorId: () => connectorId.value,
      live: () => isLive.value,
      shown: () => shown.value,
      onChange,
    })
  )
  return { connectorId, isLive, shown, onChange, scope }
}

describe("following what a catalog shows (D303)", () => {
  it("says what is shown once it settles, and listens to its topic", async () => {
    setUp()
    expect(subscribe).toHaveBeenCalledWith(CHANGES_TOPIC, expect.any(Function))
    expect(follow).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(400)

    expect(asked()).toEqual([{ connector: "c1", nodes: [null, "/app"] }])
  })

  it("says it again when what is shown changes, once for a burst", async () => {
    const { shown } = setUp()
    await vi.advanceTimersByTimeAsync(400)
    follow.mockClear()

    shown.value = [null, "/app", "/app/config"]
    await nextTick()
    shown.value = [null, "/app", "/app/config", "/lab"]
    await nextTick()
    await vi.advanceTimersByTimeAsync(400)

    expect(asked()).toEqual([{ connector: "c1", nodes: [null, "/app", "/app/config", "/lab"] }])
  })

  it("renews the watch every thirty seconds, before the server lets go of it", async () => {
    setUp()
    await vi.advanceTimersByTimeAsync(400)
    follow.mockClear()

    await vi.advanceTimersByTimeAsync(30_000)
    expect(follow).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(30_000)
    expect(follow).toHaveBeenCalledTimes(2)
  })

  it("hands on a change for its own connection and not another's", () => {
    const { onChange } = setUp()
    const mine: SourceChangesEvent = { connector_id: "c1", levels: [null], nodes: [], everything: false }

    listeners.get(CHANGES_TOPIC)?.({ ...mine, connector_id: "c2" })
    listeners.get(CHANGES_TOPIC)?.({ unrelated: true })
    listeners.get(CHANGES_TOPIC)?.(mine)

    expect(onChange.mock.calls).toEqual([[mine]])
  })

  it("asks for nothing and stops listening when the catalog closes", async () => {
    const { scope } = setUp()
    await vi.advanceTimersByTimeAsync(400)
    follow.mockClear()

    scope.stop()

    expect(stopListening).toHaveBeenCalledOnce()
    expect(asked()).toEqual([{ connector: "c1", nodes: [] }])
    await vi.advanceTimersByTimeAsync(60_000)
    expect(follow).toHaveBeenCalledTimes(1)
  })

  it("lets go of one connection before following the next", async () => {
    const { connectorId } = setUp()
    await vi.advanceTimersByTimeAsync(400)
    follow.mockClear()

    connectorId.value = "c2"
    await nextTick()
    await vi.advanceTimersByTimeAsync(400)

    expect(asked()).toEqual([
      { connector: "c1", nodes: [] },
      { connector: "c2", nodes: [null, "/app"] },
    ])
  })

  it("follows nothing for a source that tells no changes", async () => {
    const { isLive } = setUp(false)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(subscribe).not.toHaveBeenCalled()
    expect(follow).not.toHaveBeenCalled()

    isLive.value = true
    await nextTick()
    await vi.advanceTimersByTimeAsync(400)
    expect(asked()).toEqual([{ connector: "c1", nodes: [null, "/app"] }])
  })

  it("does not fail when the server refuses", async () => {
    follow.mockRejectedValue(new Error("refused"))
    setUp()
    await vi.advanceTimersByTimeAsync(400)
    expect(follow).toHaveBeenCalledOnce()
  })
})
