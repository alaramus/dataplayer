import { describe, expect, it } from "vitest"

import { claudeCommand, clientJson, isExpired } from "./mcp"

const ADDRESS = "https://data.example/mcp"
const TOKEN = "dp_mcp_abc"

describe("what a client is configured with", () => {
  it("gives Claude Code one line with the address and the token as a bearer", () => {
    expect(claudeCommand(ADDRESS, TOKEN)).toBe(
      'claude mcp add --transport http dataplayer https://data.example/mcp --header "Authorization: Bearer dp_mcp_abc"'
    )
  })

  it("gives other clients an mcpServers entry they can paste", () => {
    const parsed = JSON.parse(clientJson(ADDRESS, TOKEN)) as {
      mcpServers: Record<string, { url: string; headers: Record<string, string> }>
    }
    expect(parsed.mcpServers.dataplayer?.url).toBe(ADDRESS)
    expect(parsed.mcpServers.dataplayer?.headers.Authorization).toBe(`Bearer ${TOKEN}`)
  })
})

describe("whether a token has run out", () => {
  const now = new Date("2026-11-13T12:00:00Z")

  it("never does without an expiry", () => {
    expect(isExpired(null, now)).toBe(false)
    expect(isExpired(undefined, now)).toBe(false)
  })

  it("has at the moment it expires and after", () => {
    expect(isExpired("2026-11-13T12:00:00Z", now)).toBe(true)
    expect(isExpired("2026-11-13T11:59:00Z", now)).toBe(true)
    expect(isExpired("2026-11-13T12:01:00Z", now)).toBe(false)
  })
})
