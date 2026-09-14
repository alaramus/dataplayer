import { describe, expect, it } from "vitest"

import { composeSnippet, lastHeardWording } from "./agentSnippet"

describe("the Compose file of an agent", () => {
  const request = { key: "k3y-_x", port: 9999, serverHost: "dataplayer.example", hostname: "" }

  it("runs the agent against the host it reports, signing with the key", () => {
    const snippet = composeSnippet(request)

    expect(snippet).toContain("image: alaramus/dataplayer-monitor-agent:latest")
    expect(snippet).toContain('DPM_SERVER: "dataplayer.example:9999"')
    expect(snippet).toContain('DPM_KEY: "k3y-_x"')
    expect(snippet).toContain("pid: host")
    expect(snippet).toContain("network_mode: host")
    expect(snippet).toContain("- /:/host:ro\n")
    expect(snippet).not.toContain("DPM_HOSTNAME")
  })

  it("names the host only when a name is typed, and finds a local server on the host itself", () => {
    const snippet = composeSnippet({ ...request, serverHost: "localhost", hostname: " web-01 " })

    expect(snippet).toContain('DPM_SERVER: "127.0.0.1:9999"')
    expect(snippet).toContain('DPM_HOSTNAME: "web-01"')
  })
})

describe("when an agent was last heard from", () => {
  const now = Date.parse("2026-09-13T07:30:00Z")

  it("says never, seconds, minutes, hours and days", () => {
    expect(lastHeardWording(null, now)).toBe("Never")
    expect(lastHeardWording("2026-09-13T07:29:30Z", now)).toBe("30 s ago")
    expect(lastHeardWording("2026-09-13T07:10:00Z", now)).toBe("20 min ago")
    expect(lastHeardWording("2026-09-13T04:00:00Z", now)).toBe("3 h ago")
    expect(lastHeardWording("2026-09-10T07:30:00Z", now)).toBe("3 d ago")
  })
})
