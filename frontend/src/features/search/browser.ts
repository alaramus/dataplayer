import type { BrowserPlace } from "@/client"
import type { TabGroup } from "@/features/workspace/groups"
import { lookOf } from "@/features/workspace/panels"
import type { Panel } from "@/features/workspace/panels"
import { t } from "@/shared/i18n"
import type { MessageKey } from "@/shared/i18n"

/** The most places a request names (the server's MAX_BROWSER_PLACES). */
export const MAX_BROWSER_PLACES = 200

/** What a tab that names no connection is called beside its title. */
const KIND_WORDS: Partial<Record<Panel["kind"], MessageKey>> = {
  catalog: "search.browser.catalog",
  query: "search.browser.query",
  result: "search.browser.result",
  widget: "search.browser.widget",
  "service-logs": "search.browser.service_logs",
}

function detailOf(panel: Panel): string | undefined {
  const connection = "connectorName" in panel ? panel.connectorName : null
  if (connection !== null) return connection
  const key = KIND_WORDS[panel.kind]
  return key === undefined ? undefined : t(key)
}

/**
 * The places only the browser knows, for the search to find (S9): every open
 * tab and window by the title on its tab, then every saved tab group by its
 * name, at most 200.
 *
 * Not the Search tab, which is where the person already is, nor the
 * Connections column, which has no tab and cannot be closed: both would be
 * found by every word they share with a connection.
 */
export function browserPlacesOf(
  panels: readonly Panel[],
  groups: readonly Pick<TabGroup, "id" | "name">[]
): BrowserPlace[] {
  const places: BrowserPlace[] = []
  for (const panel of panels) {
    if (panel.kind === "search" || panel.kind === "connectors") continue
    const detail = detailOf(panel)
    places.push({
      object_type: "tab",
      object_id: panel.id,
      title: lookOf(panel).title,
      ...(detail === undefined ? {} : { detail }),
    })
  }
  for (const group of groups) {
    places.push({ object_type: "tab_group", object_id: group.id, title: group.name })
  }
  return places.slice(0, MAX_BROWSER_PLACES)
}
