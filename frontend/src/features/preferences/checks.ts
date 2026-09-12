import type { PreferencesPublic } from "@/client"

/**
 * How often the server probes this user's connections, in the words the
 * screen offers. The set is the server's, so this is a type and not a list of
 * its own; only the wording is decided here.
 */
export type CheckInterval = PreferencesPublic["connector_checks"]

/**
 * What each choice is called.
 *
 * A complete record rather than a lookup with a fallback: a choice the server
 * gains and this forgets to name is then a type error here instead of a blank
 * line in the menu.
 */
const LABELS: Record<CheckInterval, string> = {
  off: "Never — only when I press check",
  "15s": "Every 15 seconds",
  "30s": "Every 30 seconds",
  "1m": "Every minute",
  "5m": "Every 5 minutes",
  "15m": "Every 15 minutes",
}

/** The order they are offered in: never first, then longest to shortest wait. */
export const CHECK_INTERVALS: readonly CheckInterval[] = [
  "off",
  "15s",
  "30s",
  "1m",
  "5m",
  "15m",
]

export function checkIntervalLabel(interval: CheckInterval): string {
  return LABELS[interval]
}

export function checkIntervalOptions(): { label: string; value: CheckInterval }[] {
  return CHECK_INTERVALS.map((interval) => ({
    label: checkIntervalLabel(interval),
    value: interval,
  }))
}

/** Whether this choice means the dots are told nothing until asked. */
export function checksAreOff(interval: CheckInterval | undefined): boolean {
  return interval === "off"
}
