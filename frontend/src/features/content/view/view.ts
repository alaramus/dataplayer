/**
 * What a document's view is made of, read off the generated client (D420).
 *
 * The server answers a closed set of blocks and values; these names are the
 * members of its unions, so a kind added there is a type error in the switch
 * that draws it rather than a block that silently draws nothing. Plain
 * functions, so what is drawn can be tested without mounting anything.
 */
import type { DocumentView, NodeRepresentation, SectionBlock, ViewHeader, ViewPair } from "@/client"
import { formatDuration, formatSize } from "@/features/catalog/nodes"
import { ageLabel } from "@/shared/freshness/freshness"
import { t } from "@/shared/i18n"
import { formatDateTime, formatNumber } from "@/shared/i18n/format"

export type ViewBlock = DocumentView["blocks"][number]
export type SectionChild = SectionBlock["blocks"][number]
export type ViewValue = NonNullable<ViewHeader["subtitle"]>

/** Pairs are filterable from this many on: twenty fit on a screen. */
export const PAIRS_FILTERED_FROM = 20

/**
 * A value as one line of text: what a cell copies, what a filter matches and
 * what a reader hears. A sensitive pair's value never comes through here.
 */
export function valueText(value: ViewValue, now: number = Date.now()): string {
  switch (value.kind) {
    case "text":
    case "code":
    case "link":
      return value.text
    case "number":
      return value.unit ? `${formatNumber(value.value)} ${value.unit}` : formatNumber(value.value)
    case "bytes":
      return formatSize(value.value)
    case "moment":
      return `${formatDateTime(value.value)} (${momentAgo(value.value, now)})`
    case "duration":
      return formatDuration(value.seconds)
    case "boolean":
      return value.value ? t("content.view.yes") : t("content.view.no")
    case "state":
      return value.word
    case "list":
      return value.items.join(", ")
    case "empty":
    case undefined:
      return "—"
  }
}

/** How long ago an instant was, or how far ahead it is. */
export function momentAgo(value: string, now: number = Date.now()): string {
  const at = Date.parse(value)
  if (Number.isNaN(at)) return ""
  const age = now - at
  return age >= 0
    ? t("content.view.ago", { age: ageLabel(age) })
    : t("content.view.ahead", { age: ageLabel(-age) })
}

/**
 * The pairs a filter leaves, by name or by value. A hidden value is not
 * searched: a filter that matched it would say what it is.
 */
export function filterPairs(pairs: readonly ViewPair[], query: string): ViewPair[] {
  const wanted = query.trim().toLowerCase()
  if (wanted === "") return [...pairs]
  return pairs.filter(
    (pair) =>
      pair.name.toLowerCase().includes(wanted) ||
      (pair.sensitive !== true && pair.value.toLowerCase().includes(wanted))
  )
}

/** The node's other ways to open, each a button on the view (D419). */
export function otherRepresentations(
  representations: readonly NodeRepresentation[] | undefined,
  shown: NodeRepresentation["kind"]
): NodeRepresentation[] {
  return (representations ?? []).filter((one) => one.kind !== shown)
}
