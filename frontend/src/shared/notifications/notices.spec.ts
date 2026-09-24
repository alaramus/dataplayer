import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { CARDS, createNotices, FADES_AFTER } from "./notices"

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

  it("fades an error card but keeps its message in Activity", () => {
    const log = createNotices()

    log.record(trouble("Could not paste those cells"))
    expect(log.cards.value.map((card) => card.message)).toEqual(["Could not paste those cells"])
    vi.advanceTimersByTime(FADES_AFTER + 1)

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

  it("forgets one message without forgetting the rest", () => {
    const log = createNotices()
    const id = log.record(news("Copied"))
    log.record(news("Saved"))

    log.forget(id)

    expect(log.entries.value.map((entry) => entry.message)).toEqual(["Saved"])
  })
})
