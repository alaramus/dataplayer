import { describe, expect, it } from "vitest"

import { renderProse } from "./render"
import { sanitizeDocument, sanitizeFragment, sanitizeSvg } from "./sanitize"

describe("what a document may put into the page", () => {
  it("removes a script wherever the author writes it", () => {
    expect(sanitizeFragment('<p>ok</p><script>alert(1)</script>')).toBe("<p>ok</p>")
    expect(renderProse("<script>alert(1)</script>\n\ntext")).not.toContain("alert(1)")
  })

  it("removes an event handler attribute", () => {
    expect(sanitizeFragment('<img src="/a.png" onerror="alert(1)">')).not.toContain("onerror")
  })

  it("refuses an embed, a form and a button outright", () => {
    const html = sanitizeFragment(
      '<iframe src="https://example.test"></iframe><form><button>go</button></form>'
    )

    expect(html).not.toContain("iframe")
    expect(html).not.toContain("form")
    expect(html).not.toContain("button")
  })

  it("drops a javascript link", () => {
    expect(sanitizeFragment('<a href="javascript:alert(1)">x</a>')).not.toContain("javascript:")
  })

  it("leaves a relative link inert, because nothing resolves it yet", () => {
    const html = sanitizeFragment('<a href="./notes.txt">x</a>')

    expect(html).not.toContain("href")
    expect(html).toContain("data-unresolved-link")
  })

  it("sends an external link to a new window that cannot reach the opener", () => {
    const html = sanitizeFragment('<a href="https://example.test">x</a>')

    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it("keeps an anchor inside the document as it is", () => {
    expect(sanitizeFragment('<a href="#heading">x</a>')).toContain('href="#heading"')
  })

  it("does not request a remote image, and says which one it did not", () => {
    const html = sanitizeFragment('<img src="https://example.test/pixel.png">')

    expect(html).toContain("data-remote-blocked")
    expect(html).not.toContain("example.test")
  })

  it("requests a remote image once the reader asks for this document", () => {
    const html = sanitizeFragment('<img src="https://example.test/pixel.png">', {
      allowRemoteImages: true,
    })

    expect(html).toContain("example.test/pixel.png")
    expect(html).not.toContain("data-remote-blocked")
  })

  it("keeps a local image, lazy and without a referrer", () => {
    const html = sanitizeFragment('<img src="/api/v1/pixel.png">')

    expect(html).toContain('loading="lazy"')
    expect(html).toContain('referrerpolicy="no-referrer"')
  })

  it("disables a task-list checkbox instead of removing it, and removes other inputs", () => {
    const html = sanitizeFragment('<input type="checkbox"><input type="text">')

    expect(html).toContain("disabled")
    expect(html).not.toContain('type="text"')
  })

  it("keeps inline styles inside KaTeX and nowhere else", () => {
    const html = sanitizeDocument(
      '<span class="katex"><span style="height:2em">x</span></span>' +
        '<p style="position:fixed">y</p>'
    )

    expect(html).toContain('style="height:2em"')
    expect(html).not.toContain("position:fixed")
  })

  it("strips scripting out of an SVG, and its styles unless they are asked for", () => {
    const svg = '<svg><style>a{}</style><rect style="fill:red"/><script>alert(1)</script></svg>'

    expect(sanitizeSvg(svg)).not.toContain("alert(1)")
    expect(sanitizeSvg(svg)).not.toContain("fill:red")
    expect(sanitizeSvg(svg, { allowStyles: true })).toContain("fill:red")
  })
})

describe("rendering prose", () => {
  it("renders tables, task lists and inline code", () => {
    const html = renderProse(
      ["| a | b |", "| --- | --- |", "| 1 | 2 |", "", "- [x] done", "", "`code`"].join("\n")
    )

    expect(html).toContain("<table>")
    expect(html).toContain('type="checkbox"')
    expect(html).toContain("<code>code</code>")
  })

  it("renders a formula through KaTeX", () => {
    expect(renderProse("$E = mc^2$")).toContain("katex")
  })
})
