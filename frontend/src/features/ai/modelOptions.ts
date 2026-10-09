import type { AgentModelPublic, ProviderKeyState } from "@/client"
import type { SelectOption } from "@/shared/ui"

export type Provider = ProviderKeyState["provider"]
export type ModelOption = SelectOption & {
  provider?: Provider
  auto?: boolean
  /** Whose key window the row's key button opens; the row's own provider by default. */
  keyProvider?: Provider
}
/** No model row names it — the server sends it only with chat models — so the client says it once, as AI settings do. */
export const jevProviderLabel = "TypeSafe (Jev)"

/** Jev routes among the models of every provider with a configured key. */
export const AUTO_ALL_VALUE = "auto:all"

export function autoModelValue(provider: string): string {
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

/** The fallback for the all-providers choice: the current model when it is still listed, else the first model with a key. */
export function fallbackForAll(
  models: readonly AgentModelPublic[],
  currentKey: string | null,
  keyed: ReadonlySet<string>
): AgentModelPublic | undefined {
  return models.find((model) => model.key === currentKey)
    ?? models.find((model) => keyed.has(model.provider))
    ?? models[0]
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
 * One provider key changes the state shown on its heading's key button, and
 * a hairline separates the groups. The field names the chosen model with no
 * key mark beside it.
 */
export function groupedModelOptions(
  models: readonly AgentModelPublic[],
  keys: readonly ProviderKeyState[]
): ModelOption[] {
  const set = new Set(keys.filter((key) => key.set).map((key) => key.provider))
  const order = [...new Set(models.map((model) => model.provider))]
  const jevKeySet = set.has("typesafe")
  const keyedCount = order.filter((provider) => set.has(provider)).length
  // The one key this row can ask for. Without a chat key at all there is no
  // single provider to offer, so the row stays without a button.
  const allKey =
    !jevKeySet || keyedCount > 0
      ? {
          actionIcon: jevKeySet ? "key" : "key_off",
          actionLabel: `Manage ${jevProviderLabel} API key`,
          actionActive: jevKeySet,
          keyProvider: "typesafe" as Provider,
        }
      : {}
  const all: ModelOption = {
    label: "Choose with Jev (all)",
    value: AUTO_ALL_VALUE,
    auto: true,
    // The row stands on its label alone, as the models do; only a row with
    // no button to press keeps an explaining line.
    description: !jevKeySet || keyedCount > 0 ? undefined : "Set a chat provider API key first",
    disable: !jevKeySet || keyedCount === 0,
    ...allKey,
  }
  return [all, ...order.flatMap((provider) => {
    const keyIsSet = set.has(provider)
    const label = providerLabel(models, provider)
    const ready = jevKeySet && keyIsSet
    const auto: ModelOption = {
      label: `Choose with Jev (${label})`,
      value: autoModelValue(provider),
      provider,
      auto: true,
      disable: !jevKeySet || !keyIsSet,
      actionIcon: jevKeySet ? "key" : "key_off",
      actionLabel: `Manage ${jevProviderLabel} API key`,
      actionActive: jevKeySet,
      keyProvider: "typesafe",
    }
    // One line a model: nothing of the key beside it. The heading above
    // carries the key button, and the field names the chosen model plainly.
    const choices: ModelOption[] = models
      .filter((model) => model.provider === provider)
      .map((model, index) => ({
        label: model.name,
        value: model.key,
        provider,
        separator: index === 0,
      }))
    const heading: ModelOption = {
      label,
      value: `provider:${provider}`,
      group: true,
      provider,
      separator: true,
      actionIcon: keyIsSet ? "key" : "key_off",
      actionLabel: `Manage ${label} API key`,
      actionActive: keyIsSet,
      keyProvider: provider,
    }
    return [heading, auto, ...choices]
  })]
}
