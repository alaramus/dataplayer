import type { AgentModelPublic, ProviderKeyState } from "@/client"
import type { SelectOption } from "@/shared/ui"

export type Provider = ProviderKeyState["provider"]
export type ModelOption = SelectOption & { provider?: Provider }

export const providers: { id: Provider; label: string }[] = [
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "gemini", label: "Gemini" },
]

/** One provider key changes the state shown beside every model in its group. */
export function groupedModelOptions(
  models: AgentModelPublic[],
  keys: ProviderKeyState[]
): ModelOption[] {
  const set = new Set(keys.filter((key) => key.set).map((key) => key.provider))
  return providers.flatMap((provider) => {
    const keyIsSet = set.has(provider.id)
    const choices: ModelOption[] = models
      .filter((model) => model.provider === provider.id)
      .map((model) => ({
        label: model.name,
        value: model.key,
        provider: provider.id,
        description: keyIsSet ? "API key set" : "API key required",
        actionIcon: keyIsSet ? "key" : "key_off",
        actionLabel: `Manage ${provider.label} API key`,
        actionActive: keyIsSet,
      }))
    return choices.length === 0
      ? []
      : [{ label: provider.label, value: `provider:${provider.id}`, group: true }, ...choices]
  })
}
