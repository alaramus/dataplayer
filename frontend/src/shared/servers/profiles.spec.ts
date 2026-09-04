import { describe, expect, it } from "vitest"

import { normalizeServerUrl, parseProfiles, routeServerTarget, safeLocalPath, scopedServerKey, serverNavigation } from "./profiles"

describe("server addresses", () => {
  it("normalizes the origin while retaining an installation prefix", () => {
    expect(normalizeServerUrl(" HTTPS://Data.Example:443/player/// ")).toBe("https://data.example/player")
    expect(normalizeServerUrl("http://[::1]:8000/")).toBe("http://[::1]:8000")
  })

  it.each(["data.example", "ftp://data.example", "https://user:secret@data.example", "https://data.example?token=secret", "https://data.example#fragment", "https://data.example?", "https://data.example#", "https://data.example\\other", "https://data. example"])("rejects an unsafe or incomplete address: %s", (url) => {
    expect(() => normalizeServerUrl(url)).toThrow()
  })

  it("recovers valid profiles from damaged storage without duplicate destinations", () => {
    expect(parseProfiles("bad json")).toEqual([])
    expect(parseProfiles(JSON.stringify([
      { name: "First", url: "https://data.example/" },
      { name: "Updated", url: "https://data.example:443" },
      { name: "Invalid", url: "javascript:alert(1)" },
      { name: " ", url: "https://second.example" },
    ]))).toEqual([{ name: "Updated", url: "https://data.example" }])
  })

  it("keeps navigation on this frontend", () => {
    for (const path of ["https://foreign.example/", "//foreign.example/", "/\\foreign.example/", "/.//foreign.example/"]) {
      expect(safeLocalPath(path)).toBeNull()
      expect(() => serverNavigation("https://data.example", path)).toThrow()
    }
    expect(serverNavigation("https://data.example", "/s/token?server=old#view")).toBe("/s/token?server=https%3A%2F%2Fdata.example#view")
  })

  it("routes legacy shared links to the configured server before authentication", () => {
    const active = "https://other.example"
    const configured = "https://default.example"
    expect(routeServerTarget(undefined, true, active, configured)).toBe(configured)
    expect(routeServerTarget(undefined, false, active, configured)).toBeNull()
    expect(routeServerTarget(active + "/", true, active, configured)).toBeNull()
    expect(routeServerTarget("https://unknown.example", false, active, configured)).toBe("https://unknown.example")
    expect(routeServerTarget("javascript:alert(1)", true, active, configured)).toBe("javascript:alert(1)")
  })

  it("never reuses the legacy token key on a different destination", () => {
    expect(scopedServerKey("access_token", "https://a.example", "https://a.example")).toBe("access_token")
    expect(scopedServerKey("access_token", "https://b.example", "https://a.example")).not.toBe("access_token")
    expect(scopedServerKey("access_token", "https://a.example/other", "https://a.example")).not.toBe("access_token")
  })
})
