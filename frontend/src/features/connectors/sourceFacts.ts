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

const STATES: Record<Exclude<SourceFeature["state"], "available" | "absent">, string> = {
  get unsupported() { return t("connectors.facts.unsupported") },
  get unavailable() { return t("connectors.facts.unavailable") },
}

/**
 * Everything a source said, the server itself first, then every extension
 * installed in it by the name the server gives it.
 *
 * The version leads because it is the question the rest is an answer about:
 * which extension is installed means nothing until it is known which server
 * it is installed in. A feature is what the application can do with an
 * extension, so it adds nothing to the line of an extension that is there and
 * works, and an absent one is simply not in the list. Only a feature that
 * could not be used says why, and one the list missed still says its version — on its extension's line, or on a line of its
 * own when the catalog would not say what is installed at all. A source that
 * says nothing produces nothing, and the panel then shows only whether the
 * connection worked.
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
  const byCode = new Map(features.features.map((feature) => [feature.code as string, feature]))
  for (const extension of features.extensions ?? []) {
    const feature = byCode.get(extension.name)
    byCode.delete(extension.name)
    facts.push({
      code: `extension-${extension.name}`,
      label: feature?.title ?? extension.name,
      value: extension.version,
      ...(feature?.reason ? { note: feature.reason } : {}),
    })
  }
  for (const feature of byCode.values()) {
    if (feature.state === "absent") continue
    facts.push({
      code: feature.code,
      label: feature.title,
      value: feature.installed_version ?? STATES[feature.state as keyof typeof STATES],
      ...(feature.reason ? { note: feature.reason } : {}),
    })
  }
  return facts
}
