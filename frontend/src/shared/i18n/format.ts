import { currentLanguage } from "./index"

/**
 * Dates and numbers in the interface's language rather than the browser's
 * (D227). Read wherever a person reads the result, never while a module
 * loads, for the reason `t` gives.
 */

type Moment = Date | number | string

function asDate(value: Moment): Date {
  return value instanceof Date ? value : new Date(value)
}

/** A date and a time: "10/17/2026, 3:04:05 PM", «17.10.2026, 15:04:05». */
export function formatDateTime(value: Moment, options?: Intl.DateTimeFormatOptions): string {
  return asDate(value).toLocaleString(currentLanguage(), options)
}

/** A date alone: "10/17/2026", «17.10.2026». */
export function formatDate(value: Moment, options?: Intl.DateTimeFormatOptions): string {
  return asDate(value).toLocaleDateString(currentLanguage(), options)
}

/** A time of day: "3:04:05 PM", «15:04:05». */
export function formatTime(value: Moment, options?: Intl.DateTimeFormatOptions): string {
  return asDate(value).toLocaleTimeString(currentLanguage(), options)
}

/** A number as a person reads it: "4,211.5", «4 211,5». */
export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return value.toLocaleString(currentLanguage(), options)
}

/**
 * `toFixed` in the interface's language: "4.2", «4,2». Ungrouped, as
 * `toFixed` is, so English reads exactly as it did.
 */
export function formatFixed(value: number, digits: number): string {
  return formatNumber(value, { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false })
}
