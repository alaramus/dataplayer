import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { CARDS, createNotices, ERROR_FADES_AFTER, FADES_AFTER } from "./notices"

function news(message: string) {
  return { tone: "success" as const, message, action: null }
}

function trouble(message: string) {
  return { tone: "error" as const, message, action: null }
}

describe("what the application has said", () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it("shows a card and keeps the message after the card has gone", () => {
    const log = createNotices()

    log.record(news("Row inserted"))
    expect(log.cards.value.map((card) => card.message)).toEqual(["Row inserted"])

    vi.advanceTimersByTime(FADES_AFTER + 1)

    expect(log.cards.value).toEqual([])
    expect(log.entries.value.map((entry) => entry.message)).toEqual(["Row inserted"])
  })

  it("revises what a recorded entry says, where it stands, and nothing unrecorded", () => {
    const log = createNotices()
    log.record(news("Searched"), { id: "job:1", card: false })
    log.record(news("Copied"), { card: false })

    log.revise("job:1", { lines: ["Its matches are no longer held"] })
    log.revise("job:2", { message: "never" })

    expect(log.entries.value.map((entry) => [entry.message, entry.lines])).toEqual([
      ["Copied", undefined],
      ["Searched", ["Its matches are no longer held"]],
    ])
  })

  it("fades an error card later, but keeps its message in Activity", () => {
    const log = createNotices()

    log.record(trouble("Could not paste those cells"))
    expect(log.cards.value.map((card) => card.message)).toEqual(["Could not paste those cells"])
    // Missing a failure costs more than missing a success.
    vi.advanceTimersByTime(FADES_AFTER + 1)
    expect(log.cards.value).toHaveLength(1)
    vi.advanceTimersByTime(ERROR_FADES_AFTER - FADES_AFTER)

    expect(log.cards.value).toEqual([])
    expect(log.entries.value.map((entry) => entry.message)).toEqual(["Could not paste those cells"])
  })

  it("draws only the newest few, and says how many it is not drawing", () => {
    const log = createNotices()

    for (let index = 0; index < CARDS + 2; index++) log.record(trouble(`failure ${index}`))

    expect(log.cards.value.map((card) => card.message)).toEqual(["failure 2", "failure 3", "failure 4"])
    expect(log.hidden.value).toBe(2)
  })

  it("says nothing on screen while the sheet showing it is open", () => {
    const log = createNotices()
    log.setOpen(true)

    log.record(trouble("Could not read the clipboard"))

    expect(log.cards.value).toEqual([])
    expect(log.entries.value).toHaveLength(1)
  })

  it("takes the cards down when the sheet is opened, since it now says it properly", () => {
    const log = createNotices()
    log.record(trouble("Could not delete the selected rows"))

    log.setOpen(true)

    expect(log.cards.value).toEqual([])
  })

  it("records but does not interrupt while a person has asked not to be disturbed", () => {
    const log = createNotices()
    log.setDoNotDisturb(true)

    log.record(news("2 rows brought in"))

    expect(log.cards.value).toEqual([])
    expect(log.entries.value).toHaveLength(1)
  })

  it("counts what has arrived since the sheet was last looked at", () => {
    const log = createNotices()
    log.record(news("Connection saved"))
    expect(log.unseen.value).toBe(1)

    log.setOpen(true)
    log.setOpen(false)
    log.record(news("Cell updated"))

    expect(log.unseen.value).toBe(1)
  })

  it("records a thing named by an id once, however often it is seen", () => {
    // A job is read again at every poll; its ending is one entry.
    const log = createNotices()

    log.record(news("Pipeline run completed"), { id: "job:1" })
    log.record(news("Pipeline run completed"), { id: "job:1" })

    expect(log.entries.value).toHaveLength(1)
    expect(log.cards.value).toHaveLength(1)
  })

  it("keeps out what was forgotten by hand, under the same id", () => {
    const log = createNotices()
    log.record(news("Backup created"), { id: "job:2" })

    log.forget("job:2")
    log.record(news("Backup created"), { id: "job:2" })

    expect(log.entries.value).toEqual([])
  })

  it("places what happened earlier by when it happened, and does not interrupt for it", () => {
    const log = createNotices()
    log.record(news("Saved"))

    log.record(news("Transfer completed"), { id: "job:3", at: Date.now() - 60_000, card: false })

    expect(log.entries.value.map((entry) => entry.message)).toEqual(["Saved", "Transfer completed"])
    expect(log.cards.value.map((card) => card.message)).toEqual(["Saved"])
  })

  it("puts up a card for what is recorded elsewhere, without writing it into the log", () => {
    // What needs somebody is recorded in the first section of the sheet; the
    // card is only the moment it arrived (D181).
    const log = createNotices()

    log.announce({ id: "attention:job:4", tone: "error", title: "Pipeline could not be completed", message: "Stopped at 1 of 1", action: null })

    expect(log.cards.value.map((card) => card.title)).toEqual(["Pipeline could not be completed"])
    expect(log.entries.value).toEqual([])
    vi.advanceTimersByTime(ERROR_FADES_AFTER + 1)
    expect(log.cards.value).toEqual([])
  })

  it("forgets one message without forgetting the rest", () => {
    const log = createNotices()
    const id = log.record(news("Copied"))
    log.record(news("Saved"))

    log.forget(id)

    expect(log.entries.value.map((entry) => entry.message)).toEqual(["Saved"])
  })
})
