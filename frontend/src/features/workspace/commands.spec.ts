import { describe, expect, it } from "vitest"

import { connectionCommands } from "./commands"
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
  const found = bar(state).find((command) => command.name === "queries")
  if (found === undefined) throw new Error("the bar offers no queries command")
  return found
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
    const command = queries()

    expect(command.enabled).toBe(true)
    expect(command.tooltip).toBe("Queries written against local pg")
  })

  it("says to open a connection when none is being read", () => {
    const command = queries({ name: null })

    expect(command.enabled).toBe(false)
    expect(command.tooltip).toBe("Open a connection to use this")
  })

  it("says the source cannot do it when the source has said so", () => {
    const command = queries({ supportsQueries: "no" })

    expect(command.enabled).toBe(false)
    expect(command.tooltip).toBe("This source does not run queries")
  })

  it("does not claim a refusal it has not heard yet", () => {
    // Half a second of "this source does not run queries" about a PostgreSQL
    // connection is a worse answer than saying nothing.
    const command = queries({ supportsQueries: "asking" })

    expect(command.enabled).toBe(false)
    expect(command.tooltip).toBe("Asking this connection what it can do")
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
