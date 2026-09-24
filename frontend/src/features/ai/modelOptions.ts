import type { AgentModelPublic, ProviderKeyState } from "@/client"
import type { SelectOption } from "@/shared/ui"
import { appIcons } from "@/shared/ui"

export type Provider = ProviderKeyState["provider"]
export type ModelOption = SelectOption & { provider?: Provider; auto?: boolean }

export function autoModelValue(provider: AgentModelPublic["provider"]): string {
  return `auto:${provider}`
}

export function fallbackModel(
  models: readonly AgentModelPublic[],
  currentKey: string | null,
  provider: AgentModelPublic["provider"]
): AgentModelPublic | undefined {
  const current = models.find((model) => model.key === currentKey)
  return current?.provider === provider ? current : models.find((model) => model.provider === provider)
}

/** What the server calls a provider, from the models it sent. */
export function providerLabel(models: readonly AgentModelPublic[], provider: Provider): string {
  return models.find((model) => model.provider === provider)?.provider_label ?? provider
}

/**
 * The models under their providers, in the order and by the names the server
 * sends.
 *
 * The client keeps no list of providers: it had one, and the models of a
 * provider added on the server but not to that list never reached the screen.
 * One provider key changes the state shown beside every model in its group.
 *
 * `keyInField` also draws that state after the chosen model's name; a caller
 * with a key button beside the field says it there instead.
 */
export function groupedModelOptions(
  models: readonly AgentModelPublic[],
  keys: readonly ProviderKeyState[],
  { keyInField = true }: { keyInField?: boolean } = {}
): ModelOption[] {
  const set = new Set(keys.filter((key) => key.set).map((key) => key.provider))
  const order = [...new Set(models.map((model) => model.provider))]
  return order.flatMap((provider) => {
    const keyIsSet = set.has(provider)
    const jevKeySet = set.has("typesafe")
    const label = providerLabel(models, provider)
    const auto: ModelOption = {
      label: "Choose with Jev",
      value: autoModelValue(provider),
      provider,
      auto: true,
      icon: appIcons.autoAwesome,
      description: !jevKeySet ? "Set the Jev API key in AI settings" : keyIsSet
        ? `Jev selects from every ${label} model`
        : `${label} API key required`,
      disable: !jevKeySet || !keyIsSet,
    }
    const choices: ModelOption[] = models
      .filter((model) => model.provider === provider)
      .map((model) => ({
        label: model.name,
        value: model.key,
        provider,
        description: keyIsSet ? "API key set" : "API key required",
        actionIcon: keyIsSet ? "key" : "key_off",
        actionLabel: `Manage ${label} API key`,
        actionActive: keyIsSet,
        ...(keyInField ? { stateIcon: keyIsSet ? "key" : "key_off", stateActive: keyIsSet } : {}),
      }))
    return [{ label, value: `provider:${provider}`, group: true }, auto, ...choices]
  })
}
