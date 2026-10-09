import { describe, expect, it } from "vitest"

import type { AgentModelPublic } from "@/client"
import { AUTO_ALL_VALUE, fallbackForAll, fallbackModel, groupedModelOptions } from "./modelOptions"
import type { Provider } from "./modelOptions"

const models: AgentModelPublic[] = [
  { key: "anthropic:a", provider: "anthropic", provider_label: "Anthropic", id: "a", name: "Claude A", context_window: 1, max_output_tokens: 1, reasoning: true, image_input: false, available: false },
  { key: "anthropic:b", provider: "anthropic", provider_label: "Anthropic", id: "b", name: "Claude B", context_window: 1, max_output_tokens: 1, reasoning: false, image_input: false, available: false },
  { key: "openai:a", provider: "openai", provider_label: "OpenAI", id: "a", name: "GPT A", context_window: 1, max_output_tokens: 1, reasoning: false, image_input: false, available: false },
]

describe("grouped model choices", () => {
  it("groups models by provider, in the server's order and words", () => {
    expect(groupedModelOptions(models, []).map((option) => option.label)).toEqual([
      "Choose with Jev (all)", "Anthropic", "Choose with Jev (Anthropic)", "Claude A", "Claude B", "OpenAI", "Choose with Jev (OpenAI)", "GPT A",
    ])
  })

  // The client once kept its own list of providers, and a model of one the
  // list lacked never reached the screen.
  it("shows a provider only the server knows, by the name it sends", () => {
    const newcomer = { ...models[2]!, key: "mistral:a", provider: "mistral", provider_label: "Mistral" } as unknown as AgentModelPublic
    const options = groupedModelOptions([newcomer], [])
    expect(options.map((option) => option.label)).toEqual(["Choose with Jev (all)", "Mistral", "Choose with Jev (Mistral)", "GPT A"])
    expect(options[1]?.actionLabel).toBe("Manage Mistral API key")
  })

  it("keeps the key on the provider heading rather than on every model", () => {
    const options = groupedModelOptions(models, [{ provider: "anthropic", set: true }])
    const heading = options.find((option) => option.group && option.provider === "anthropic")
    expect(heading?.description).toBeUndefined()
    expect(heading?.actionIcon).toBe("key")
    expect(heading?.actionLabel).toBe("Manage Anthropic API key")
    expect(heading?.keyProvider).toBe("anthropic")
    const rows = options.filter((option) => option.provider === "anthropic" && !option.group && !option.auto)
    expect(rows).toHaveLength(2)
    expect(rows.every((option) => option.actionIcon === undefined)).toBe(true)
    expect(rows.every((option) => option.description === undefined)).toBe(true)
    expect(rows.every((option) => option.stateIcon === undefined)).toBe(true)
  })

  it("separates the provider groups and the models from their Jev row", () => {
    const options = groupedModelOptions(models, [])
    expect(options[0]?.value).toBe(AUTO_ALL_VALUE)
    expect(options.filter((option) => option.separator).map((option) => option.value)).toEqual([
      "provider:anthropic", "anthropic:a", "provider:openai", "openai:a",
    ])
  })

  it("offers every provider's models through Jev only when both keys exist", () => {
    const missing = groupedModelOptions(models, [{ provider: "anthropic", set: true }])
    expect(missing.find((option) => option.value === "auto:anthropic")?.disable).toBe(true)

    const ready = groupedModelOptions(models, [
      { provider: "anthropic", set: true }, { provider: "typesafe", set: true },
    ])
    expect(ready.find((option) => option.value === "auto:anthropic")?.disable).toBe(false)
    expect(ready.find((option) => option.value === "auto:openai")?.disable).toBe(true)
    expect(fallbackModel(models, "anthropic:b", "anthropic")?.key).toBe("anthropic:b")
    expect(fallbackModel(models, "openai:a", "anthropic")?.key).toBe("anthropic:a")
  })

  it("offers Jev across all providers only when its key and a chat key exist", () => {
    const noJev = groupedModelOptions(models, [{ provider: "anthropic", set: true }])
    expect(noJev.find((option) => option.value === AUTO_ALL_VALUE)?.disable).toBe(true)

    const noChatKey = groupedModelOptions(models, [{ provider: "typesafe", set: true }])
    expect(noChatKey.find((option) => option.value === AUTO_ALL_VALUE)?.disable).toBe(true)

    const ready = groupedModelOptions(models, [
      { provider: "openai", set: true }, { provider: "typesafe", set: true },
    ])
    const all = ready.find((option) => option.value === AUTO_ALL_VALUE)
    expect(all?.disable).toBe(false)
    expect(all?.label).toBe("Choose with Jev (all)")
    expect(all?.description).toBeUndefined()
  })

  it("says and opens the one Jev key from every Jev row", () => {
    const noJev = groupedModelOptions(models, [{ provider: "anthropic", set: true }])
    for (const value of [AUTO_ALL_VALUE, "auto:anthropic"]) {
      const row = noJev.find((option) => option.value === value)
      expect(row?.actionIcon).toBe("key_off")
      expect(row?.keyProvider).toBe("typesafe")
      expect(row?.description).toBeUndefined()
    }

    // The provider's own key lives on its heading: the Jev row keeps saying
    // the Jev key even while that one is missing.
    const noChatKey = groupedModelOptions(models, [{ provider: "typesafe", set: true }])
    const blocked = noChatKey.find((option) => option.value === "auto:anthropic")
    expect(blocked?.actionIcon).toBe("key")
    expect(blocked?.keyProvider).toBe("typesafe")
    expect(blocked?.description).toBeUndefined()
    expect(noChatKey.find((option) => option.value === AUTO_ALL_VALUE)?.actionIcon).toBeUndefined()

    const ready = groupedModelOptions(models, [
      { provider: "anthropic", set: true }, { provider: "typesafe", set: true },
    ])
    const open = ready.find((option) => option.value === "auto:anthropic")
    expect(open?.actionIcon).toBe("key")
    expect(open?.keyProvider).toBe("typesafe")
    expect(open?.description).toBeUndefined()
  })

  it("keeps the current model as the all-providers fallback only while it has a key", () => {
    expect(fallbackForAll(models, "openai:a", new Set<Provider>(["openai", "anthropic"]))?.key).toBe("openai:a")
    // The server refuses a fallback whose provider has no key (D157).
    expect(fallbackForAll(models, "openai:a", new Set<Provider>(["anthropic"]))?.key).toBe("anthropic:a")
    expect(fallbackForAll(models, "openai:retired", new Set<Provider>(["anthropic"]))?.key).toBe("anthropic:a")
    expect(fallbackForAll(models, null, new Set())).toBeUndefined()
    expect(fallbackForAll([], null, new Set())).toBeUndefined()
  })
})
