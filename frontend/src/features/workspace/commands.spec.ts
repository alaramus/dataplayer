import { describe, expect, it } from "vitest"

import { queriesCommand, servicesCommand } from "./commands"
import type { ConnectionState } from "./commands"

function queries(state: Partial<ConnectionState> = {}) {
  return queriesCommand({
    name: "local pg",
    supportsQueries: "yes",
    ...state,
  })
}

describe("what the bar says about the library of queries", () => {
  it("opens whether or not a connection is being read", () => {
    // A query outlives the connection it was written against, and the library
    // has a filter of its own for choosing which one to look at. Greying it
    // out made the one place a person's own work lives reachable only through
    // somebody else's database.
    expect(queries().enabled).toBe(true)
    expect(queries({ name: null }).enabled).toBe(true)
    expect(queries({ supportsQueries: "no" }).enabled).toBe(true)
  })

  it("says which connection it would open against, when there is one", () => {
    expect(queries().tooltip).toBe("Queries written against local pg")
  })

  it("says what it holds when there is not", () => {
    expect(queries({ name: null }).tooltip).toBe("Every query you have written")
    // And when the open connection is one that runs nothing: the library is
    // still every query, rather than a refusal about this database.
    expect(queries({ supportsQueries: "no" }).tooltip).toBe(
      "Every query you have written"
    )
  })
})

describe("what the bar says about the services this server runs", () => {
  it("opens even while nothing is running, and says so", () => {
    // The panel it opens says there is nothing, which is an answer too; a
    // greyed-out button left the question of where services live unanswered.
    const command = servicesCommand({ count: 0, working: null })

    expect(command.enabled).toBe(true)
    expect(command.tooltip).toBe("This server is not running anything for you")
  })

  it("says how many there are once there are any", () => {
    expect(servicesCommand({ count: 1, working: null }).tooltip).toBe(
      "One service is running here"
    )
    expect(servicesCommand({ count: 3, working: null }).enabled).toBe(true)
    expect(servicesCommand({ count: 3, working: null }).tooltip).toBe(
      "3 services are running here"
    )
  })

  it("says the step while something is happening, even before the first one exists", () => {
    // The window that asked for it has closed by then, so this is the only
    // place a start is visible.
    const command = servicesCommand({
      count: 1,
      working: "demo: pulling the image (2 of 6)",
    })

    expect(command.enabled).toBe(true)
    expect(command.tooltip).toBe("demo: pulling the image (2 of 6)")
  })
})
