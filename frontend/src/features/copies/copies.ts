import { ref } from "vue"

import type { CopyBrief } from "@/client"
import { type MessageKey, t } from "@/shared/i18n"
import { formatNumber } from "@/shared/i18n/format"

/** Whether the copy history window is open (D460); drawn once by the workspace. */
const open = ref(false)

export function useCopiesWindow() {
  return {
    open,
    toggle() {
      open.value = !open.value
    },
    close() {
      open.value = false
    },
  }
}

const SOURCES: Record<CopyBrief["source"], MessageKey> = {
  grid: "copies.source.grid",
  agent: "copies.source.agent",
  catalog: "copies.source.catalog",
  code: "copies.source.code",
  connection: "copies.source.connection",
  document: "copies.source.document",
  view: "copies.source.view",
  link: "copies.source.link",
  log: "copies.source.log",
  record: "copies.source.record",
  key: "copies.source.key",
  other: "copies.source.other",
}

/** Where a copy came from, as the line under it says: "Grid · email". */
export function originLine(copy: Pick<CopyBrief, "source" | "detail">): string {
  const source = t(SOURCES[copy.source])
  return copy.detail ? `${source} · ${copy.detail}` : source
}

/** What the line says of a copy's size when the list shows only its start. */
export function sizeLine(copy: Pick<CopyBrief, "length" | "cut" | "preview">): string | null {
  if (copy.cut) return t("copies.window.cut", { n: formatNumber(copy.length) })
  if (copy.preview.length < copy.length) return t("copies.window.longer", { n: formatNumber(copy.length) })
  return null
}

/**
 * The ids chosen that the list still shows: a search or another tab can take
 * a copy away while it is ticked, and deleting it again would count nothing.
 */
export function chosenShown(chosen: ReadonlySet<string>, shown: readonly Pick<CopyBrief, "id">[]): string[] {
  return shown.filter((copy) => chosen.has(copy.id)).map((copy) => copy.id)
}
