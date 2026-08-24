import type { CheckReport } from "@/stores/connectorChecks"

/**
 * What state a connection is in, and how to say it in words.
 *
 * Two readers: the dot takes the tone, the icon around it takes the words for
 * its tooltip. The dot cannot carry the tooltip itself — it is drawn on top of
 * the icon with pointer events off, so nothing would ever hover it.
 *
 * Pure, so the rule is tested without mounting anything.
 */
export type ConnectorState = "disabled" | "unknown" | "ok" | "failed"

export interface StateDescription {
  state: ConnectorState
  words: string
}

/** How long ago, so a stale dot cannot pass for a fresh one. */
export function ageInWords(checkedAt: string, now: number): string {
  const seconds = Math.max(0, Math.round((now - Date.parse(checkedAt)) / 1000))
  if (seconds < 60) return `${String(seconds)}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${String(minutes)} min ago`
  return `${String(Math.round(minutes / 60))} h ago`
}

export function describeState(
  enabled: boolean,
  report: CheckReport | null,
  now: number = Date.now()
): StateDescription {
  // Being switched off wins over anything remembered: nobody is probing it, so
  // nothing else could still be true of it.
  if (!enabled) return { state: "disabled", words: "Switched off" }
  if (!report) return { state: "unknown", words: "Not checked yet" }
  return {
    state: report.ok ? "ok" : "failed",
    words: `${report.message} · ${ageInWords(report.checkedAt, now)}`,
  }
}
