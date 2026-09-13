/**
 * What the store window says about the store, and what removing it takes with
 * it. Pure, so the wording is tested without a window.
 */

import type { StoreUsage, TierInfo } from "@/client"

import { duration, formatValue } from "./seriesFormat"

export function tierWording(tier: TierInfo): string {
  const what = tier.width_seconds === 0 ? "Samples as they came" : `Averages over ${duration(tier.width_seconds)}`
  return `${what}: kept ${duration(tier.kept_seconds)}`
}

export function sizeWording(usage: StoreUsage): string {
  if (usage.bytes === null || usage.bytes === undefined) return "Not answering, so not measured"
  const series = usage.series ?? 0
  return `${formatValue(usage.bytes, "B")} on disk, ${String(series)} series`
}

export function originWording(usage: StoreUsage): string {
  return usage.origin === "started"
    ? `TimescaleDB started on this server, at ${usage.address}`
    : `An existing TimescaleDB, at ${usage.address}`
}

/** The warning a removal is confirmed against: whose data goes, and what stays. */
export function removalWarning(usage: StoreUsage): string {
  const lost = "every sample of every person, and every chart and tile on every dashboard. "
    + "Process tables stay on their dashboards, and agents keep their keys."
  return usage.origin === "started"
    ? `The container is removed with its data: ${lost}`
    : `Dashboards stop using ${usage.address} and drop the tables they kept there: ${lost} `
      + "The database itself stays."
}
