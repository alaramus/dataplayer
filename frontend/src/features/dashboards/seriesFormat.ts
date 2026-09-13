/**
 * A value as a person reads it, by the unit its series was stored with.
 *
 * Values are stored as reported (D130); scaling is presentation and lives
 * here. Kilobytes, bytes and bit rates move to the nearest binary step,
 * seconds become a duration, a percentage keeps one decimal.
 */

const BYTE_STEPS = ["B", "KB", "MB", "GB", "TB", "PB"]
const BIT_STEPS = ["b/s", "Kb/s", "Mb/s", "Gb/s", "Tb/s"]
const BYTES_PER: Record<string, number> = { B: 1, kB: 1024, MB: 1024 ** 2, GB: 1024 ** 3 }

function short(value: number): string {
  const magnitude = Math.abs(value)
  if (magnitude >= 100 || Number.isInteger(value)) return value.toFixed(0)
  if (magnitude >= 10) return value.toFixed(1)
  return value.toFixed(2)
}

function stepped(value: number, steps: string[]): string {
  let scaled = value
  let index = 0
  while (Math.abs(scaled) >= 1024 && index < steps.length - 1) {
    scaled /= 1024
    index += 1
  }
  return `${short(scaled)} ${steps[index] ?? ""}`
}

export function duration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (days > 0) return hours > 0 ? `${String(days)} d ${String(hours)} h` : `${String(days)} d`
  if (hours > 0) return minutes > 0 ? `${String(hours)} h ${String(minutes)} min` : `${String(hours)} h`
  if (minutes > 0) return `${String(minutes)} min`
  return `${String(total)} s`
}

export function formatValue(value: number, unit: string): string {
  if (unit.endsWith("/s") && unit !== "b/s") {
    // A connection's counter, read as a rate: bytes step like bytes, a count
    // keeps a short number.
    const base = unit.slice(0, -2)
    return base === "" ? `${short(value)} /s` : `${formatValue(value, base)}/s`
  }
  const bytes = BYTES_PER[unit]
  if (bytes !== undefined) return stepped(value * bytes, BYTE_STEPS)
  if (unit === "b/s") return stepped(value, BIT_STEPS)
  if (unit === "%") return `${value.toFixed(1)} %`
  if (unit === "s") return duration(value)
  if (unit === "") return short(value)
  return `${short(value)} ${unit}`
}
