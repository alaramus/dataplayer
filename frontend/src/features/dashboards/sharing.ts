/**
 * What a person may do with a dashboard, and its address. Pure, so the rules
 * the screen follows are tested without mounting it; the rules themselves are
 * the server's, which sends the standing (D129).
 */

import type { DashboardPublic } from "@/client"
import { t } from "@/shared/i18n"

import type { SeriesEntry } from "./catalog"

export type DashboardLevel = "read" | "write"

// Labels are getters: read at render, in the language current then (D224).
export const DASHBOARD_LEVELS: { readonly label: string; value: DashboardLevel }[] = [
  { get label() { return t("dashboards.share.can_view") }, value: "read" },
  { get label() { return t("dashboards.share.can_edit") }, value: "write" },
]

export function levelLabel(level: DashboardLevel): string {
  return DASHBOARD_LEVELS.find((one) => one.value === level)?.label ?? level
}

/** Whether what is on the dashboard, its name and its options are saved. */
export function mayEdit(dashboard: Pick<DashboardPublic, "access">): boolean {
  return dashboard.access !== "read"
}

/** Whether its grants are managed and it is deleted: its owner's alone. */
export function mayManage(dashboard: Pick<DashboardPublic, "access">): boolean {
  return (dashboard.access ?? "own") === "own"
}

/** The address of a dashboard where the person reading it is. */
export function dashboardLinkFor(dashboardId: string, origin: string, serverUrl?: string): string {
  const link = new URL(`/dashboards/${encodeURIComponent(dashboardId)}`, origin)
  if (serverUrl !== undefined) link.searchParams.set("server", serverUrl)
  return link.href
}

/** The caller's own dashboards first, then those shared with them. */
export function splitByOwner<T extends Pick<DashboardPublic, "access">>(dashboards: readonly T[]): { own: T[]; shared: T[] } {
  return {
    own: dashboards.filter((one) => mayManage(one)),
    shared: dashboards.filter((one) => !mayManage(one)),
  }
}

/**
 * Names for the series a widget draws: what the person reads directly, and
 * what the dashboard lets them read through it. The first wins, being the
 * fresher of two answers about one series.
 */
export function mergedIndex(
  direct: Map<number, SeriesEntry>,
  through: Map<number, SeriesEntry>
): Map<number, SeriesEntry> {
  return new Map([...through, ...direct])
}
