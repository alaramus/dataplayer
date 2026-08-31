import { describe, expect, it } from "vitest"

import { languageFor } from "./language"

describe("content editor language selection", () => {
  it("recognises source files through CodeMirror's filename metadata", () => {
    expect(languageFor("worker.py")?.name).toBe("Python")
    expect(languageFor("component.vue")?.name).toBe("Vue")
    expect(languageFor("README.md")?.name).toBe("Markdown")
  })

  it("lets a source hint override an unfamiliar filename", () => {
    expect(languageFor("events.ndjson", "json")?.name).toBe("JSON")
  })
})
