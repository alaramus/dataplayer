import { describe, expect, it } from "vitest"

import type { AdapterTypeInfo, ConnectorPublic } from "@/client"

import {
  afterClosing,
  nextOrdinal,
  terminalCandidates,
  terminalNotice,
  terminalPress,
  terminalPressTooltip,
  terminalTitle,
} from "./terminals"

function connector(overrides: Partial<ConnectorPublic> = {}): ConnectorPublic {
  return {
    id: "c1",
    name: "prod",
    adapter_type: "ssh",
    access: "own",
    enabled: true,
    ...overrides,
  } as ConnectorPublic
}

function type(name: string, codes: string[]): AdapterTypeInfo {
  return {
    name,
    capabilities: codes.map((code) => ({ group: "manage", title: code, code })),
  } as AdapterTypeInfo
}

const TYPES = [type("ssh", ["terminal"]), type("file", ["search"])]

describe("where a terminal can be opened", () => {
  it("is on a connection of one's own, switched on, whose type has a shell", () => {
    const offered = terminalCandidates(
      [
        connector(),
        connector({ id: "c2", access: "structure" }),
        connector({ id: "c3", enabled: false }),
        connector({ id: "c4", adapter_type: "file" }),
      ],
      TYPES
    )

    expect(offered.map((one) => one.id)).toEqual(["c1"])
  })
})

describe("pressing the Terminals button", () => {
  const base = { shown: false, inData: true, activeConnectorId: "c1", candidateIds: ["c1"], open: [] }

  it("hides the tool when it is the one shown", () => {
    expect(terminalPress({ ...base, shown: true })).toEqual({ kind: "hide" })
  })

  it("opens a terminal on the connection being worked in, when it has none", () => {
    expect(terminalPress(base)).toEqual({ kind: "open", connectorId: "c1" })
  })

  it("only shows the panel outside the Data space, for the person to choose", () => {
    // Dashboards and the agent cover the data columns: the connection that was
    // being worked in is not what is in front, and opening a shell on it would
    // come out of nowhere.
    expect(terminalPress({ ...base, inData: false })).toEqual({ kind: "show" })
  })

  it("brings forward the latest terminal of that connection, when it has one", () => {
    const open = [
      { id: "t1", connectorId: "c1", ordinal: 1 },
      { id: "t2", connectorId: "c9", ordinal: 1 },
      { id: "t3", connectorId: "c1", ordinal: 2 },
    ]

    expect(terminalPress({ ...base, open })).toEqual({ kind: "select", terminalId: "t3" })
  })

  it("only shows the panel outside a connection that has a shell", () => {
    expect(terminalPress({ ...base, activeConnectorId: null })).toEqual({ kind: "show" })
    expect(terminalPress({ ...base, activeConnectorId: "c2" })).toEqual({ kind: "show" })
  })

  it("says what it will do, and how many are open", () => {
    expect(terminalPressTooltip({ kind: "open", connectorId: "c1" }, "prod", 0)).toBe(
      "Open a terminal on prod"
    )
    expect(terminalPressTooltip({ kind: "hide" }, "prod", 0)).toBe("Hide the terminals")
    expect(terminalPressTooltip({ kind: "show" }, null, 2)).toBe("Terminals · 2 open")
  })
})

describe("what a terminal is called", () => {
  it("is its connection's name, numbered from the second on", () => {
    expect(terminalTitle({ id: "t1", connectorId: "c1", ordinal: 1 }, "prod")).toBe("prod")
    expect(terminalTitle({ id: "t2", connectorId: "c1", ordinal: 2 }, "prod")).toBe("prod (2)")
  })

  it("keeps its number when an earlier one closes", () => {
    const open = [
      { id: "t1", connectorId: "c1", ordinal: 1 },
      { id: "t3", connectorId: "c1", ordinal: 3 },
    ]

    expect(nextOrdinal(open, "c1")).toBe(4)
    expect(nextOrdinal(open, "c2")).toBe(1)
  })
})

describe("closing a terminal", () => {
  const open = [
    { id: "t1", connectorId: "c1", ordinal: 1 },
    { id: "t2", connectorId: "c1", ordinal: 2 },
    { id: "t3", connectorId: "c1", ordinal: 3 },
  ]

  it("brings its neighbour forward when it was in front", () => {
    expect(afterClosing(open, "t2", "t2")).toBe("t3")
    expect(afterClosing(open, "t3", "t3")).toBe("t2")
  })

  it("leaves the one in front where it is otherwise", () => {
    expect(afterClosing(open, "t1", "t3")).toBe("t3")
  })

  it("leaves nothing in front after the last", () => {
    expect(afterClosing(open.slice(0, 1), "t1", "t1")).toBeNull()
  })
})

describe("what is said above a terminal", () => {
  it("is nothing while the shell runs", () => {
    expect(terminalNotice({ kind: "open" })).toBeNull()
  })

  it("offers to open a locked key, and to try again after anything else", () => {
    expect(
      terminalNotice({ kind: "refused", code: "source", message: "Locked", errorKind: "locked" })
        ?.action
    ).toBe("unlock")
    expect(
      terminalNotice({ kind: "refused", code: "source", message: "Down", errorKind: "network" })
        ?.action
    ).toBe("again")
    expect(terminalNotice({ kind: "lost" })?.action).toBe("again")
  })

  it("names a status other than success", () => {
    expect(terminalNotice({ kind: "ended", exitStatus: 0 })?.text).toBe("The shell has ended")
    expect(terminalNotice({ kind: "ended", exitStatus: 130 })?.text).toBe(
      "The shell has ended with status 130"
    )
  })
})
