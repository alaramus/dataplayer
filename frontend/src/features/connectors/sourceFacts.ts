import type { SourceFeature, SourceFeatures } from "@/client"
import { t } from "@/shared/i18n"

/**
 * What a source said about itself, as lines to read.
 *
 * Plain functions, so the wording is tested without mounting the panel that
 * shows it. The panel is the one after a check, because that is the moment
 * somebody is asking what they are about to work on — it used to sit in the
 * connection's Options, where nobody looking for it would think to open it.
 */
export interface SourceFact {
  /** What the fact is about: the server, or one of its optional features. */
  label: string
  /** What it says, in one line. */
  value: string
  /** Why it says that, where the source gave a reason. */
  note?: string
  /** Addresses one fact in a test, as `source-fact-<code>`. */
  code: string
}

const STATES: Record<Exclude<SourceFeature["state"], "available">, string> = {
  get absent() { return t("connectors.facts.absent") },
  get unsupported() { return t("connectors.facts.unsupported") },
  get unavailable() { return t("connectors.facts.unavailable") },
}

/** What one optional feature says: its version, or why there is none. */
export function featureFact(feature: SourceFeature): SourceFact {
  const state = STATES[feature.state as Exclude<SourceFeature["state"], "available">]
  return {
    code: feature.code,
    label: feature.title,
    value: feature.installed_version ?? state,
    ...(feature.reason ? { note: feature.reason } : {}),
  }
}

/**
 * Everything a source said, the server itself first.
 *
 * The version leads because it is the question the rest is an answer about:
 * which TimescaleDB is installed means nothing until it is known which server
 * it is installed in. A source that says nothing produces nothing, and the
 * panel then shows only whether the connection worked.
 */
export function sourceFacts(
  features: SourceFeatures | null | undefined,
  sourceTitle: string
): SourceFact[] {
  if (!features) return []
  const facts: SourceFact[] = []
  if (features.server_version) {
    facts.push({
      code: "server",
      label: sourceTitle,
      value: features.server_version,
    })
  }
  return [...facts, ...features.features.map(featureFact)]
}
