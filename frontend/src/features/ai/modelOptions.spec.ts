import { describe, expect, it } from "vitest"

import type { AgentModelPublic } from "@/client"
import { groupedModelOptions } from "./modelOptions"

const models: AgentModelPublic[] = [
  { key: "anthropic:a", provider: "anthropic", id: "a", name: "Claude A", context_window: 1, max_output_tokens: 1, reasoning: true, image_input: false, available: false },
  { key: "anthropic:b", provider: "anthropic", id: "b", name: "Claude B", context_window: 1, max_output_tokens: 1, reasoning: false, image_input: false, available: false },
  { key: "openai:a", provider: "openai", id: "a", name: "GPT A", context_window: 1, max_output_tokens: 1, reasoning: false, image_input: false, available: false },
]

describe("grouped model choices", () => {
  it("groups models by provider", () => {
    expect(groupedModelOptions(models, []).map((option) => option.label)).toEqual([
      "OpenAI", "GPT A", "Anthropic", "Claude A", "Claude B",
    ])
  })

  it("marks every model of a provider when its one key is set", () => {
    const options = groupedModelOptions(models, [{ provider: "anthropic", set: true }])
      .filter((option) => option.provider === "anthropic")
    expect(options).toHaveLength(2)
    expect(options.every((option) => option.actionIcon === "key")).toBe(true)
    expect(options.every((option) => option.description === "API key set")).toBe(true)
    expect(options.every((option) => option.stateIcon === "key" && option.stateActive)).toBe(true)
  })

  it("leaves the key out of the field where a button beside it says so", () => {
    const options = groupedModelOptions(models, [], { keyInField: false })
    expect(options.some((option) => option.stateIcon !== undefined)).toBe(false)
    expect(options.filter((option) => !option.group).every((option) => option.actionIcon === "key_off")).toBe(true)
  })
})
