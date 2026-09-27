/**
 * A pipeline's schedule as the screen words it and edits it (D179). When it
 * comes next is the server's answer; these only say it and shape the form.
 */

import type { ScheduleSettings } from "@/client"

export type IntervalUnit = "minutes" | "hours" | "days"

const UNIT_MINUTES: Record<IntervalUnit, number> = { minutes: 1, hours: 60, days: 24 * 60 }
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const
export const WEEKDAYS = [0, 1, 2, 3, 4] as const
export const EVERY_DAY = [0, 1, 2, 3, 4, 5, 6] as const
/** The server's bound on the times of a day, said before one is added. */
export const MAX_TIMES = 12

/** The browser's time zone, which the schedule's times are read in. */
export function browserZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

/** A schedule never set: off, and every night at 03:00 once it is switched on. */
export function firstSettings(zone: string): ScheduleSettings {
  return { enabled: false, kind: "times", every_minutes: 60, times: ["03:00"], days: [...EVERY_DAY], time_zone: zone }
}

/** An interval as the form shows it: the largest unit it is a whole number of. */
export function intervalParts(minutes: number): { count: number; unit: IntervalUnit } {
  for (const unit of ["days", "hours"] as const) {
    if (minutes % UNIT_MINUTES[unit] === 0) return { count: minutes / UNIT_MINUTES[unit], unit }
  }
  return { count: minutes, unit: "minutes" }
}

export function minutesOf(count: number, unit: IntervalUnit): number {
  return Math.round(count * UNIT_MINUTES[unit])
}

function counted(count: number, noun: string): string {
  return count === 1 ? `${noun}` : `${String(count)} ${noun}s`
}

function joined(parts: readonly string[]): string {
  return parts.length <= 1 ? parts.join("") : `${parts.slice(0, -1).join(", ")} and ${parts.at(-1) ?? ""}`
}

function daysWords(days: readonly number[]): string {
  const sorted = [...new Set(days)].sort((a, b) => a - b)
  if (sorted.length === 7) return "Every day"
  if (sorted.join() === WEEKDAYS.join()) return "Weekdays"
  if (sorted.join() === "5,6") return "Weekends"
  return sorted.map((day) => DAY_NAMES[day] ?? "").join(", ")
}

/** What the schedule does, in a line: "Every 5 minutes", "Weekdays at 09:00 and 18:00". */
export function scheduleWords(settings: ScheduleSettings | null | undefined): string {
  if (!settings?.enabled) return "Runs only when Run is pressed"
  if (settings.kind === "interval") {
    const { count, unit } = intervalParts(settings.every_minutes ?? 60)
    return `Every ${counted(count, unit.slice(0, -1))}`
  }
  return `${daysWords(settings.days ?? [])} at ${joined([...(settings.times ?? [])].sort())}`
}

export const TIME: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }

/** When it runs next, in this browser's clock: "today 03:00", "tomorrow 03:00", "Mon 09:00". */
export function nextRunWords(nextAt: string | null | undefined, now: number): string | null {
  const at = Date.parse(nextAt ?? "")
  if (Number.isNaN(at)) return null
  const moment = new Date(at)
  const clock = moment.toLocaleTimeString("en-GB", TIME)
  const day = (time: number) => new Date(time).toDateString()
  if (day(at) === day(now)) return `today ${clock}`
  if (day(at) === day(now + 24 * 60 * 60 * 1000)) return `tomorrow ${clock}`
  if (at - now < 6 * 24 * 60 * 60 * 1000) return `${moment.toLocaleDateString("en-GB", { weekday: "short" })} ${clock}`
  return `${moment.toLocaleDateString("en-GB", { day: "numeric", month: "short" })} ${clock}`
}
