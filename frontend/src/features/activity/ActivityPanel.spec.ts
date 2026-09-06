import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { notices, resetNotices } from "@/shared/notifications"
import type { AttentionItem } from "@/shared/notifications"
import ActivityPanel from "./ActivityPanel.vue"
import type { ProcessRow } from "./presentation"

const running: ProcessRow = {
  id: "job-1", source: "server", label: "Start service · analytics-pg",
  detail: "pulling the image (1 of 6)", status: "Running", tone: "info",
  active: true, paused: false, progress: null, measurement: "",
  createdAt: Date.now(), canPause: false, canResume: false, canStop: true,
  controlsHint: "Cancellation keeps completed changes.",
}

function waiting(overrides: Partial<AttentionItem> = {}): AttentionItem {
  return {
    id: "access:req-1", tone: "info",
    title: "Ivan is asking for access to prod-db",
    detail: "Through a link to orders", at: Date.now(),
    action: null, dismiss: null, ...overrides,
  }
}

// Teleported into the body, so what a test mounted has to be taken down again
// or the next one reads the last one's sheet.
let sheet: ReturnType<typeof mount> | null = null

function open(attention: AttentionItem[] = [], rows: ProcessRow[] = []) {
  sheet = mount(ActivityPanel, {
    attachTo: document.body,
    props: {
      attention, rows, error: "", loading: false, more: false,
      stopping: new Set<string>(), bottom: 24,
    },
    global: { plugins: [Quasar] },
  })
  return sheet
}

describe("the activity sheet", () => {
  beforeEach(() => { resetNotices() })
  afterEach(() => {
    sheet?.unmount()
    sheet = null
    resetNotices()
  })

  it("keeps what is waiting, what is running and what was said apart", () => {
    notices().record({ tone: "success", message: "Connection saved", sticky: false, action: null })

    open([waiting()], [running])

    const sections = ["attention-section", "working-section", "recent-section"].map(
      (name) => document.querySelector(`[data-testid="${name}"]`)?.textContent ?? ""
    )
    expect(sections[0]).toContain("Ivan is asking for access to prod-db")
    expect(sections[1]).toContain("Start service · analytics-pg")
    expect(sections[2]).toContain("Connection saved")
    // A message about something that happened is not something waiting.
    expect(sections[0]).not.toContain("Connection saved")
  })

  it("says so plainly when nothing is waiting, rather than leaving the reader to guess", () => {
    open([], [running])

    expect(document.querySelector('[data-testid="attention-section"]')?.textContent)
      .toContain("Nothing is waiting for you")
  })

  it("leads to where a thing is answered instead of answering it here", async () => {
    const run = vi.fn()
    open([waiting({ action: { label: "Open", run } })])

    const button = [...document.querySelectorAll("button")].find(
      (element) => element.textContent?.includes("Open")
    )
    button?.click()
    await Promise.resolve()

    expect(run).toHaveBeenCalled()
  })

  it("offers no way to wave away something that is still waiting on an answer", () => {
    open([waiting()])

    const dismissals = document.querySelectorAll(
      '[data-testid="attention-access:req-1"] [aria-label], [data-testid="attention-access:req-1"] button'
    )
    expect(dismissals).toHaveLength(0)
  })

  it("closes on Escape, because it is a flyout and not a piece of work", async () => {
    const wrapper = open()

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted("close")).toBeTruthy()
  })
})
