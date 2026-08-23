import { describe, expect, it } from "vitest"

import { sceneStage } from "./scene"

describe("what the scene says", () => {
  it("says what the application is while there is nothing to connect to", () => {
    expect(sceneStage({ loading: false, connectorCount: 0, activeConnectorId: null })).toBe(
      "no-connections"
    )
  })

  it("sends the user to the list once there is something in it", () => {
    expect(sceneStage({ loading: false, connectorCount: 2, activeConnectorId: null })).toBe(
      "pick-connection"
    )
  })

  it("sends the user to the catalog once one is open", () => {
    expect(sceneStage({ loading: false, connectorCount: 2, activeConnectorId: "c1" })).toBe(
      "pick-node"
    )
  })

  it("says nothing at all until the list has been read", () => {
    // Otherwise the first paint of every session invites the user to add a
    // connection they may already have.
    expect(sceneStage({ loading: true, connectorCount: 0, activeConnectorId: null })).toBe(
      "loading"
    )
  })

  it("keeps to the catalog while the list is still being read", () => {
    expect(sceneStage({ loading: true, connectorCount: 0, activeConnectorId: "c1" })).toBe(
      "pick-node"
    )
  })
})
