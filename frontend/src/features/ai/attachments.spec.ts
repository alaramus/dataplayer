import { describe, expect, it } from "vitest"

import type { AttachmentRules } from "@/client"

import { acceptFor, admit, kindOf, shownSize } from "./attachments"

const RULES: AttachmentRules = {
  max_files: 3,
  max_image_bytes: 5 * 1024 * 1024,
  max_text_bytes: 256 * 1024,
  max_total_bytes: 6 * 1024 * 1024,
  image_types: ["image/png", "image/jpeg"],
}
const READER = { name: "Claude Sonnet 5", readsImages: true }
const BLIND = { name: "DeepSeek V4 Flash", readsImages: false }

function file(name: string, type: string, bytes: number): File {
  return new File([new Uint8Array(bytes)], name, { type })
}

describe("files for a message", () => {
  it("tells an image from text by the type the browser reports", () => {
    expect(kindOf(file("a.png", "image/png", 1), RULES)).toBe("image")
    expect(kindOf(file("a.md", "text/markdown", 1), RULES)).toBe("text")
    expect(kindOf(file("a.log", "", 1), RULES)).toBe("text")
  })

  it("offers images in the picker only to a model that reads them", () => {
    expect(acceptFor(RULES, true)).toContain("image/png")
    expect(acceptFor(RULES, false)).not.toContain("image/")
    expect(acceptFor(RULES, false)).toContain(".csv")
  })

  it("takes what the rules allow and says why about the rest", () => {
    const photo = file("photo.png", "image/png", 1024)
    const notes = file("notes.md", "text/markdown", 1024)
    const sheet = file("book.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 10)
    const huge = file("huge.txt", "text/plain", 300 * 1024)

    expect(admit([photo, notes], [], RULES, READER)).toEqual({ taken: [photo, notes], refused: [] })
    expect(admit([photo, notes], [], RULES, BLIND)).toEqual({
      taken: [notes],
      refused: ["DeepSeek V4 Flash does not read images"],
    })
    expect(admit([sheet, huge], [], RULES, READER).refused).toEqual([
      "book.xlsx is neither text nor a PNG, JPEG, WebP or GIF image",
      "huge.txt is larger than 256 KB of text",
    ])
  })

  it("counts what the message already holds", () => {
    const held = [file("1.txt", "text/plain", 1), file("2.txt", "text/plain", 1)]
    const result = admit([file("3.txt", "text/plain", 1), file("4.txt", "text/plain", 1)], held, RULES, READER)
    expect(result.taken).toHaveLength(1)
    expect(result.refused).toEqual(["A message carries at most 3 files"])

    const big = [file("a.png", "image/png", 4 * 1024 * 1024)]
    expect(admit([file("b.png", "image/png", 3 * 1024 * 1024)], big, RULES, READER).refused).toEqual([
      "The files of one message come to more than 6 MB",
    ])
  })

  it("says a size the way a person reads it", () => {
    expect(shownSize(512)).toBe("512 B")
    expect(shownSize(1536)).toBe("1.5 KB")
    expect(shownSize(3 * 1024 * 1024)).toBe("3.0 MB")
  })
})
