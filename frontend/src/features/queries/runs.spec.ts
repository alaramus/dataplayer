/* eslint-disable vue/one-component-per-file -- two hosts for two ways of watching a run, not components of the application. */
import { QueryClient, VueQueryPlugin, focusManager } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { defineComponent, h } from "vue"

import { QueriesService } from "@/client"
import type { RunPublic } from "@/client"

import { runKey, useRun, useRunHistory } from "./runs"

beforeEach(() => {
  vi.restoreAllMocks()
})

describe("watching a run", () => {
  /** What a console would show of one run: its status, and nothing else. */
  function watching(runId: string) {
    const Host = defineComponent({
      setup() {
        const run = useRun(runId)
        return () => h("div", run.data.value?.status ?? "")
      },
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return mount(Host, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
  }

  const answer = (status: string) => ({ data: { id: "r1", status, statements: [] } }) as never

  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    // The focus manager is one object for every client in the process.
    focusManager.setFocused(undefined)
    vi.useRealTimers()
  })

  it("reads a run through to its end while the page is hidden", async () => {
    // A background tab, or a pane nobody is looking at.
    focusManager.setFocused(false)
    const reading = vi
      .spyOn(QueriesService, "readRun")
      .mockResolvedValueOnce(answer("running"))
      .mockResolvedValue(answer("succeeded"))
    const wrapper = watching("r1")
    await flushPromises()
    expect(wrapper.text()).toBe("running")

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(wrapper.text()).toBe("succeeded")

    // And stops asking once there is nothing left to wait for.
    await vi.advanceTimersByTimeAsync(5000)
    expect(reading).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})

describe("the history while a run is watched", () => {
  function run(status: RunPublic["status"], startedAt = "2026-09-27T10:00:00Z"): RunPublic {
    return {
      id: "r1",
      connector_id: "c1",
      document_id: "d1",
      document_revision: 1,
      status,
      mode: "read",
      scope: "statement",
      timeout_seconds: 30,
      statement_count: 1,
      started_at: startedAt,
    }
  }

  function answers(...states: RunPublic[]) {
    const spy = vi.spyOn(QueriesService, "readRun")
    for (const state of states) spy.mockResolvedValueOnce({ data: state } as never)
  }

  /** A console watching run r1 beside the history list, as the screen has them. */
  function watching() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const listRuns = vi
      .spyOn(QueriesService, "listRuns")
      .mockResolvedValue({ data: { data: [], count: 0 } } as never)
    let read!: ReturnType<typeof useRun>
    const Host = defineComponent({
      setup() {
        read = useRun("r1")
        useRunHistory(null, "")
        return () => h("div")
      },
    })
    const wrapper = mount(Host, {
      global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
    })
    return { client, listRuns, read, wrapper }
  }

  it("is read again when the run it lists as running has ended", async () => {
    answers(run("running"), run("succeeded"))
    const { listRuns, read, wrapper } = watching()
    await flushPromises()
    expect(read.data.value?.status).toBe("running")
    expect(listRuns).toHaveBeenCalledTimes(1)

    await read.refetch()
    await flushPromises()

    expect(read.data.value?.status).toBe("succeeded")
    expect(listRuns).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it("is read again when the end arrives with a cancel rather than a poll", async () => {
    answers(run("running"))
    const { client, listRuns, wrapper } = watching()
    await flushPromises()

    client.setQueryData(runKey("r1"), run("cancelled"))
    await flushPromises()

    expect(listRuns).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it("is left alone by a poll that finds the run still going", async () => {
    answers(run("running"), run("running", "2026-09-27T10:00:01Z"))
    const { listRuns, read, wrapper } = watching()
    await flushPromises()

    await read.refetch()
    await flushPromises()

    expect(read.data.value?.started_at).toBe("2026-09-27T10:00:01Z")
    expect(listRuns).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it("is left alone by a run that was already over when first read", async () => {
    // A pinned or previous result is read this way, long after it finished.
    answers(run("succeeded"))
    const { listRuns, read, wrapper } = watching()
    await flushPromises()

    expect(read.data.value?.status).toBe("succeeded")
    expect(listRuns).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
