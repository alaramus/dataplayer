import { describe, expect, it } from "vitest"

import type { ProblemDetail } from "@/client"

import { isProblem, wordProblem } from "./problems"

const notFound: ProblemDetail = { code: "users.not_found", params: {}, message: "User not found" }

describe("a refusal the server coded", () => {
  it("is told apart from the other shapes of detail", () => {
    expect(isProblem(notFound)).toBe(true)
    expect(isProblem({ kind: "network", message: "Unreachable" })).toBe(false)
    expect(isProblem("a sentence")).toBe(false)
    expect(isProblem(null)).toBe(false)
  })

  it("is the server's English when there is no dictionary", () => {
    expect(wordProblem(notFound, null)).toBe("User not found")
  })

  it("is the dictionary's sentence with its parameters filled in by name", () => {
    const detail = {
      ...notFound,
      params: { name: "orders", count: 3 },
    } as ProblemDetail

    expect(
      wordProblem(detail, { "users.not_found": "{count} строки в «{name}», а {missing} нет" })
    ).toBe("3 строки в «orders», а {missing} нет")
  })

  // A newer server than this build: English is better than a blank.
  it("falls back to English for a code the dictionary does not have", () => {
    expect(wordProblem(notFound, {})).toBe("User not found")
  })
})
