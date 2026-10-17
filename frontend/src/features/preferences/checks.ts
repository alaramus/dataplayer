import type { PreferencesPublic } from "@/client"
import { t } from "@/shared/i18n"

/**
 * How often the server probes this user's connections, in the words the
 * screen offers. The set is the server's, so this is a type and not a list of
 * its own; only the wording is decided here.
 */
export type CheckInterval = PreferencesPublic["connector_checks"]

/** The order they are offered in: never first, then longest to shortest wait. */
export const CHECK_INTERVALS: readonly CheckInterval[] = [
  "off",
  "15s",
  "30s",
  "1m",
  "5m",
  "15m",
]

/**
 * What a choice is called. The dictionary's `interval` group is typed by the
 * same keys, so a choice the server gains and nobody names fails to compile
 * rather than showing a blank line in the menu.
 */
export function checkIntervalLabel(interval: CheckInterval): string {
  return t(`preferences.interval.${interval}`)
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
