import { describe, expect, it } from "vitest"

import { pageOfLink } from "./links"

describe("pageOfLink", () => {
  it("names the page a link to another page of the guide points at", () => {
    expect(pageOfLink("connections.md")).toBe("connections")
    expect(pageOfLink("source-redis.md#connecting")).toBe("source-redis")
  })

  it("is nothing for a link that is not a page of the guide", () => {
    expect(pageOfLink("https://example.com/a.md")).toBeNull()
    expect(pageOfLink("../secrets.md")).toBeNull()
    expect(pageOfLink("notes.txt")).toBeNull()
    expect(pageOfLink("Connections.md")).toBeNull()
  })
})
