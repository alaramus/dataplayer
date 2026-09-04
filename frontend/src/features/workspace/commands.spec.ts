import { describe, expect, it } from "vitest"

import { connectionCommands, queriesCommand, servicesCommand } from "./commands"
import type { ConnectionState } from "./commands"

function bar(state: Partial<ConnectionState> = {}) {
  return connectionCommands({
    name: "local pg",
    supportsQueries: "yes",
    supportsBackups: "yes",
    ...state,
  })
}

function queries(state: Partial<ConnectionState> = {}) {
  return queriesCommand({
    name: "local pg",
    supportsQueries: "yes",
    supportsBackups: "yes",
    ...state,
  })
}

describe("what the bar at the foot of the screen offers", () => {
  it("keeps its shape whatever is open", () => {
    // Greyed out rather than hidden: a bar that changes shape as somebody
    // walks about is a bar they have to read every time.
    expect(bar().map((command) => command.name)).toEqual(
      bar({ name: null }).map((command) => command.name)
    )
  })

  it("offers a command of a connection that can do it", () => {
    const command = bar().find((one) => one.name === "backups")

    expect(command?.enabled).toBe(true)
  })

  it("says to open a connection when none is being read", () => {
    const command = bar({ name: null }).find((one) => one.name === "backups")

    expect(command?.enabled).toBe(false)
    expect(command?.tooltip).toBe("Open a connection to use this")
  })
})

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

describe("what the bar says about copying a database out", () => {
  function backups(state: Partial<ConnectionState> = {}) {
    const found = bar(state).find((command) => command.name === "backups")
    if (found === undefined) throw new Error("the bar offers no backups command")
    return found
  }

  it("offers it when this server can", () => {
    expect(backups().enabled).toBe(true)
    expect(backups().tooltip).toBe("Copy local pg out, or put a backup back")
  })

  it("says the server's own reason when it cannot", () => {
    // About the machine rather than about the source: no runtime to run
    // pg_dump in, or nowhere to write what it produces (D87).
    const command = backups({
      supportsBackups: "no",
      backupsRefusal: "This server has nowhere to write a backup",
    })

    expect(command.enabled).toBe(false)
    expect(command.tooltip).toBe("This server has nowhere to write a backup")
  })

  it("says so when the source is not one that can be copied out", () => {
    // The other half of the question, read off the type's capabilities: a
    // file source and a Redis server name no program that would dump them,
    // and the route answers 501 to anyone who presses it anyway.
    const command = backups({
      supportsBackups: "no",
      backupsRefusal: "This kind of connection cannot be copied out",
    })

    expect(command.enabled).toBe(false)
    expect(command.tooltip).toBe("This kind of connection cannot be copied out")
  })

  it("says nothing about it before the server has answered", () => {
    expect(backups({ supportsBackups: "asking" }).enabled).toBe(false)
  })
})

describe("what the bar says about the services this server runs", () => {
  it("is not pressable while there is nothing to open", () => {
    const command = servicesCommand({ count: 0, working: null })

    expect(command.enabled).toBe(false)
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
