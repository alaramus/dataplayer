import { describe, expect, it } from "vitest"

import { svgFromDataUrl } from "./blockActions"

describe("taking the SVG out of what a chart hands back", () => {
  it("decodes the markup after the comma", () => {
    const markup = '<svg width="10"><rect fill="#fff"/></svg>'
    const dataUrl = `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(markup)}`

    expect(svgFromDataUrl(dataUrl)).toBe(markup)
  })

  it("says nothing rather than guessing when there is no comma", () => {
    expect(svgFromDataUrl("data:image/svg+xml")).toBe("")
  })

  it("says nothing when the encoding is broken", () => {
    expect(svgFromDataUrl("data:image/svg+xml,%E0%A4%A")).toBe("")
  })
})
