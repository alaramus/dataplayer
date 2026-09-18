import { describe, expect, it } from "vitest"

import type { ConversationMessagePublic } from "@/client"
import { markAt, outlineMarks } from "./outline"

function message(
  id: string,
  role: ConversationMessagePublic["role"],
  content: string
): ConversationMessagePublic {
  return { id, role, content, run_id: null, created_at: null }
}

describe("the contents of a conversation", () => {
  it("marks the questions and not the answers", () => {
    const marks = outlineMarks([
      message("1", "user", "Count the orders"),
      message("2", "assistant", "There are 12."),
      message("3", "user", "And the customers?"),
    ])

    expect(marks).toEqual([
      { id: "1", label: "Count the orders" },
      { id: "3", label: "And the customers?" },
    ])
  })

  it("names a mark by the first line that says anything", () => {
    const [mark] = outlineMarks([message("1", "user", "\n   \nShow me the tables\nin test")])

    expect(mark?.label).toBe("Show me the tables")
  })

  it("cuts a long line rather than carrying a paragraph in a tooltip", () => {
    const [mark] = outlineMarks([message("1", "user", "word ".repeat(40))])

    expect(mark?.label.length).toBe(80)
    expect(mark?.label.endsWith("…")).toBe(true)
  })
})

describe("where the reader is", () => {
  const offsets = [{ id: "a", top: 0 }, { id: "b", top: 400 }, { id: "c", top: 900 }]

  it("stays on a question while its answer is read", () => {
    expect(markAt(offsets, 500)).toBe("b")
  })

  it("is the first before anything has been scrolled", () => {
    expect(markAt(offsets, 0)).toBe("a")
  })

  it("is nothing at all in a conversation with no questions", () => {
    expect(markAt([], 120)).toBeNull()
  })
})
