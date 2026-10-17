/**
 * A pipeline's schedule as the screen words it and edits it (D179). When it
 * comes next is the server's answer; these only say it and shape the form.
 */

import type { ScheduleSettings } from "@/client"
import { currentLanguage, t } from "@/shared/i18n"

export type IntervalUnit = "minutes" | "hours" | "days"

const UNIT_MINUTES: Record<IntervalUnit, number> = { minutes: 1, hours: 60, days: 24 * 60 }
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
  return { enabled: true, kind: "times", every_minutes: 60, times: ["03:00"], days: [...EVERY_DAY], time_zone: zone }
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

// 1 January 2024 was a Monday, the first day of the server's week.
const MONDAY = new Date(2024, 0, 1)

/** The days of the week, Monday first, as the current language shortens them: "Mon", "пн". */
export function dayNames(): string[] {
  const format = new Intl.DateTimeFormat(currentLanguage(), { weekday: "short" })
  return Array.from({ length: 7 }, (_, day) =>
    format.format(new Date(MONDAY.getFullYear(), MONDAY.getMonth(), MONDAY.getDate() + day))
  )
}

// Named by the dictionary rather than by the locale: ICU versions shorten
// September as "Sep" or as "Sept", so one browser would name a day differently
// from another.
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"] as const

/**
 * A day of a month, the year too when asked: "26 Sep", "31 Dec 2025". The
 * order is the same in every language spoken so far, so only the month is a word.
 */
export function dayMonth(moment: Date, withYear = false): string {
  const month = t(`pipelines.when.months.${MONTHS[moment.getMonth()] ?? "jan"}`)
  const day = `${String(moment.getDate())} ${month}`
  return withYear ? `${day} ${String(moment.getFullYear())}` : day
}

function counted(count: number, unit: IntervalUnit): string {
  return count === 1
    ? t(`pipelines.schedule.every_one.${unit}`)
    : t(`pipelines.schedule.every_n.${unit}`, { n: count }, count)
}

function joined(parts: readonly string[]): string {
  if (parts.length <= 1) return parts.join("")
  return t("pipelines.schedule.and", { list: parts.slice(0, -1).join(", "), last: parts.at(-1) ?? "" })
}

function daysWords(days: readonly number[]): string {
  const sorted = [...new Set(days)].sort((a, b) => a - b)
  if (sorted.length === 7) return t("pipelines.schedule.every_day")
  if (sorted.join() === WEEKDAYS.join()) return t("pipelines.schedule.weekdays")
  if (sorted.join() === "5,6") return t("pipelines.schedule.weekends")
  const names = dayNames()
  return sorted.map((day) => names[day] ?? "").join(", ")
}

/** What the schedule does, in a line: "Every 5 minutes", "Weekdays at 09:00 and 18:00". */
export function scheduleWords(settings: ScheduleSettings | null | undefined): string {
  if (!settings?.enabled) return t("pipelines.schedule.manual")
  if (settings.kind === "interval") {
    const { count, unit } = intervalParts(settings.every_minutes ?? 60)
    return counted(count, unit)
  }
  return t("pipelines.schedule.days_at", {
    days: daysWords(settings.days ?? []),
    times: joined([...(settings.times ?? [])].sort()),
  })
}

export const TIME: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }

/** A time of day in this browser's clock, always on twenty-four hours: "03:00". */
export function clockOf(moment: Date): string {
  // A fixed locale rather than the interface's (D227): HH:MM on twenty-four
  // hours in every language, the way the schedule's own times are written.
  return moment.toLocaleTimeString("en-GB", TIME)
}

/** When it runs next, in this browser's clock: "today 03:00", "tomorrow 03:00", "Mon 09:00". */
export function nextRunWords(nextAt: string | null | undefined, now: number): string | null {
  const at = Date.parse(nextAt ?? "")
  if (Number.isNaN(at)) return null
  const moment = new Date(at)
  const clock = clockOf(moment)
  const day = (time: number) => new Date(time).toDateString()
  if (day(at) === day(now)) return t("pipelines.when.today", { time: clock })
  if (day(at) === day(now + 24 * 60 * 60 * 1000)) return t("pipelines.when.tomorrow", { time: clock })
  if (at - now < 6 * 24 * 60 * 60 * 1000) {
    const weekday = moment.toLocaleDateString(currentLanguage(), { weekday: "short" })
    return `${weekday} ${clock}`
  }
  return `${dayMonth(moment)} ${clock}`
}
