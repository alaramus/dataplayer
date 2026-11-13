import { describe, expect, it } from "vitest"

import type { McpServerPublic } from "@/client"

import { createBody, formOf, updateBody } from "./mcpServers"

const saved: McpServerPublic = {
  id: "s1",
  name: "Tracker",
  url: "https://tracker.example/mcp",
  has_token: true,
  header_names: ["X-Team"],
  enabled: true,
  tools_off: [],
  created_at: "2026-11-13T00:00:00Z",
  updated_at: "2026-11-13T00:00:00Z",
}

describe("the body an MCP server's window sends", () => {
  it("sends a new server's token and headers, and none for an empty token", () => {
    const form = { ...formOf(null), name: " Tracker ", url: "https://t/mcp", headers: [{ name: "X-A", value: "1" }] }
    expect(createBody(form)).toEqual({
      name: "Tracker",
      url: "https://t/mcp",
      token: null,
      headers: { "X-A": "1" },
      enabled: true,
    })
  })

  it("leaves a saved server's secrets alone when nothing was typed", () => {
    const body = updateBody(formOf(saved), saved)
    expect(body.token).toBeNull()
    expect(body.clear_token).toBe(false)
    expect(body.headers).toBeNull()
  })

  it("keeps an untouched header's value and sends a new one", () => {
    const form = formOf(saved)
    form.headers.push({ name: "X-New", value: "v" })
    expect(updateBody(form, saved).headers).toEqual({ "X-Team": null, "X-New": "v" })
  })

  it("drops a removed header and clears the token only when asked", () => {
    const form = { ...formOf(saved), headers: [], clearToken: true }
    const body = updateBody(form, saved)
    expect(body.headers).toEqual({})
    expect(body.clear_token).toBe(true)
  })
})
