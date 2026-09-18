import { describe, expect, it } from "vitest"

import type { AgentModelPublic } from "@/client"
import { groupedModelOptions } from "./modelOptions"

const models: AgentModelPublic[] = [
  { key: "anthropic:a", provider: "anthropic", provider_label: "Anthropic", id: "a", name: "Claude A", context_window: 1, max_output_tokens: 1, reasoning: true, image_input: false, available: false },
  { key: "anthropic:b", provider: "anthropic", provider_label: "Anthropic", id: "b", name: "Claude B", context_window: 1, max_output_tokens: 1, reasoning: false, image_input: false, available: false },
  { key: "openai:a", provider: "openai", provider_label: "OpenAI", id: "a", name: "GPT A", context_window: 1, max_output_tokens: 1, reasoning: false, image_input: false, available: false },
]

describe("grouped model choices", () => {
  it("groups models by provider, in the server's order and words", () => {
    expect(groupedModelOptions(models, []).map((option) => option.label)).toEqual([
      "Anthropic", "Claude A", "Claude B", "OpenAI", "GPT A",
    ])
  })

  // The client once kept its own list of providers, and a model of one the
  // list lacked never reached the screen.
  it("shows a provider only the server knows, by the name it sends", () => {
    const newcomer = { ...models[2]!, key: "mistral:a", provider: "mistral", provider_label: "Mistral" } as unknown as AgentModelPublic
    const options = groupedModelOptions([newcomer], [])
    expect(options.map((option) => option.label)).toEqual(["Mistral", "GPT A"])
    expect(options[1]?.actionLabel).toBe("Manage Mistral API key")
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
