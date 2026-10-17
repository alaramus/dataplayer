/**
 * What the store window says about the store, and what removing it takes with
 * it. Pure, so the wording is tested without a window.
 */

import type { StoreUsage, TierInfo } from "@/client"
import { t } from "@/shared/i18n"

import { duration, formatValue } from "./seriesFormat"

export function tierWording(tier: TierInfo): string {
  const what = tier.width_seconds === 0
    ? t("dashboards.store.raw")
    : t("dashboards.store.averages", { duration: duration(tier.width_seconds) })
  return t("dashboards.store.tier", { what, duration: duration(tier.kept_seconds) })
}

export function sizeWording(usage: StoreUsage): string {
  if (usage.bytes === null || usage.bytes === undefined) return t("dashboards.store.not_measured")
  const series = usage.series ?? 0
  return t("dashboards.store.on_disk", { size: formatValue(usage.bytes, "B"), n: series }, series)
}

export function originWording(usage: StoreUsage): string {
  return usage.origin === "started"
    ? t("dashboards.store.started_origin", { address: usage.address })
    : t("dashboards.store.existing_origin", { address: usage.address })
}

/** The warning a removal is confirmed against: whose data goes, and what stays. */
export function removalWarning(usage: StoreUsage): string {
  const lost = t("dashboards.store.lost")
  return usage.origin === "started"
    ? t("dashboards.store.remove_started", { lost })
    : t("dashboards.store.remove_existing", { address: usage.address, lost })
}
