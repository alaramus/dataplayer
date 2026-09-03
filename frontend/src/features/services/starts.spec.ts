import { describe, expect, it } from "vitest"

import { buildStart, canStart } from "./starts"
import type { StartForm } from "./starts"

function form(over: Partial<StartForm> = {}): StartForm {
  return {
    mode: "chosen",
    name: "orders",
    user: "reader",
    database: "shop",
    publish: true,
    sampleData: true,
    choosable: ["user", "database"],
    offersSampleData: true,
    ...over,
  }
}

describe("what a filled-in start form means", () => {
  it("says nothing at all when it is automatic", () => {
    // Not even the name: somebody who has not been asked for one has not got
    // one in mind, and every other answer is the server's.
    expect(buildStart(form({ mode: "automatic" }))).toEqual({ mode: "automatic" })
  })

  it("carries what was chosen, trimmed", () => {
    expect(buildStart(form({ name: "  orders  ", user: " reader " }))).toEqual({
      mode: "chosen",
      name: "orders",
      user: "reader",
      database: "shop",
      publish: true,
      sample_data: true,
    })
  })

  it("leaves out a field the person left empty", () => {
    const built = buildStart(form({ user: "   ", database: "" }))

    expect(built).toMatchObject({ user: null, database: null })
  })

  it("does not send a value for a slot the template did not open", () => {
    // A Redis server has no role and no named database; the server refuses a
    // request that names one, and a form that sends what will be refused is a
    // form that lies.
    const built = buildStart(form({ choosable: [] }))

    expect(built).toMatchObject({ user: null, database: null })
  })

  it("does not ask for sample data where the source has none", () => {
    expect(buildStart(form({ offersSampleData: false }))).toMatchObject({
      sample_data: false,
    })
  })
})

describe("whether the form can be sent", () => {
  it("needs a name only when one was asked for", () => {
    expect(canStart(form({ mode: "automatic", name: "" }))).toBe(true)
    expect(canStart(form({ name: "" }))).toBe(false)
    expect(canStart(form({ name: "  " }))).toBe(false)
    expect(canStart(form({ name: "orders" }))).toBe(true)
  })
})
