/**
 * A value as a person reads it, by the unit its series was stored with.
 *
 * Values are stored as reported (D130); scaling is presentation and lives
 * here. Kilobytes, bytes and bit rates move to the nearest binary step,
 * seconds become a duration, a percentage keeps one decimal.
 */

import { t } from "@/shared/i18n"
import type { MessageKey } from "@/shared/i18n"
import { formatFixed } from "@/shared/i18n/format"

/** The words of each step, worded when a value is; the units a series is stored with stay data. */
const BYTE_STEPS: MessageKey[] = [
  "dashboards.units.b",
  "dashboards.units.kb",
  "dashboards.units.mb",
  "dashboards.units.gb",
  "dashboards.units.tb",
  "dashboards.units.pb",
]
const BIT_STEPS: MessageKey[] = [
  "dashboards.units.bps",
  "dashboards.units.kbps",
  "dashboards.units.mbps",
  "dashboards.units.gbps",
  "dashboards.units.tbps",
]
const BYTES_PER: Record<string, number> = { B: 1, kB: 1024, MB: 1024 ** 2, GB: 1024 ** 3 }

function short(value: number): string {
  const magnitude = Math.abs(value)
  if (magnitude >= 100 || Number.isInteger(value)) return formatFixed(value, 0)
  if (magnitude >= 10) return formatFixed(value, 1)
  return formatFixed(value, 2)
}

function stepped(value: number, steps: readonly MessageKey[]): string {
  let scaled = value
  let index = 0
  while (Math.abs(scaled) >= 1024 && index < steps.length - 1) {
    scaled /= 1024
    index += 1
  }
  const step = steps[index]
  return `${short(scaled)} ${step === undefined ? "" : t(step)}`
}

export function duration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (days > 0) {
    return hours > 0 ? t("dashboards.duration.days_hours", { d: days, h: hours }) : t("dashboards.duration.days", { d: days })
  }
  if (hours > 0) {
    return minutes > 0
      ? t("dashboards.duration.hours_minutes", { h: hours, m: minutes })
      : t("dashboards.duration.hours", { h: hours })
  }
  if (minutes > 0) return t("dashboards.duration.minutes", { m: minutes })
  return t("dashboards.duration.seconds", { s: total })
}

export function formatValue(value: number, unit: string): string {
  if (unit.endsWith("/s") && unit !== "b/s") {
    // A connection's counter, read as a rate: bytes step like bytes, a count
    // keeps a short number.
    const base = unit.slice(0, -2)
    return base === ""
      ? t("dashboards.units.count_per_second", { value: short(value) })
      : t("dashboards.units.per_second", { value: formatValue(value, base) })
  }
  const bytes = BYTES_PER[unit]
  if (bytes !== undefined) return stepped(value * bytes, BYTE_STEPS)
  if (unit === "b/s") return stepped(value, BIT_STEPS)
  if (unit === "%") return `${formatFixed(value, 1)} %`
  if (unit === "s") return duration(value)
  if (unit === "") return short(value)
  return `${short(value)} ${unit}`
}
