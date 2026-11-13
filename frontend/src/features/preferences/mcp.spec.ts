import { describe, expect, it } from "vitest"

import { MCP_CLIENTS, claudeCommand, clientJson, isExpired } from "./mcp"

const ADDRESS = "https://data.example/mcp"
const TOKEN = "dp_mcp_abc"

function client(id: string) {
  const found = MCP_CLIENTS.find((one) => one.id === id)
  if (found === undefined) throw new Error(`no client ${id}`)
  return found
}

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

  it("names each client once, and every one carries the address and the token", () => {
    const ids = MCP_CLIENTS.map((one) => one.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const one of MCP_CLIENTS) {
      const text = one.snippet(ADDRESS, TOKEN)
      expect(text, one.id).toContain(ADDRESS)
      expect(text, one.id).toContain(`Bearer ${TOKEN}`)
    }
  })

  it("writes every file a client reads as JSON as JSON it can read", () => {
    for (const one of MCP_CLIENTS) {
      if (one.place.kind !== "file" || !one.place.file.endsWith(".json")) continue
      expect(() => JSON.parse(one.snippet(ADDRESS, TOKEN)) as unknown, one.id).not.toThrow()
    }
  })

  it("puts the options before the name and the address where a CLI expects them", () => {
    expect(client("gemini").snippet(ADDRESS, TOKEN)).toBe(
      'gemini mcp add --transport http --header "Authorization: Bearer dp_mcp_abc" dataplayer https://data.example/mcp'
    )
    expect(client("kimi").snippet(ADDRESS, TOKEN)).toBe(
      'kimi mcp add --transport http --header "Authorization: Bearer dp_mcp_abc" dataplayer https://data.example/mcp'
    )
  })

  it("gives Codex a table of its config.toml, and VS Code its own key", () => {
    expect(client("codex").snippet(ADDRESS, TOKEN)).toBe(
      [
        "[mcp_servers.dataplayer]",
        'url = "https://data.example/mcp"',
        'http_headers = { "Authorization" = "Bearer dp_mcp_abc" }',
      ].join("\n")
    )
    const vscode = JSON.parse(client("vscode").snippet(ADDRESS, TOKEN)) as { servers?: unknown; mcpServers?: unknown }
    expect(vscode.servers).toBeDefined()
    expect(vscode.mcpServers).toBeUndefined()
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
