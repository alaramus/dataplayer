import { computed } from "vue"
import type { Ref } from "vue"

import type {
  ArrivingReference,
  FetchColumn,
  FetchReference,
  ReferencedRows,
} from "@/client"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { useToast } from "@/shared/ui"

import { useArrivingReferences, useFollowReference } from "./api"
import { keyValues, referencesLedBy } from "./references"

/**
 * The ways in and out of one row, wherever a row is shown: the key that leads
 * away (D36) and the keys landing on it that lead back (D110).
 *
 * Written once so the grid and the row view cannot drift into two answers
 * about which cell offers what, or copy a constraint onto every column it
 * touches. What differs between the
 * callers is only which columns are on screen.
 */
const NO_REFERENCES: FetchReference[] = []
const NO_ARRIVING: ArrivingReference[] = []

export interface RowReferences {
  /** The ways out drawn in this cell, for this row. */
  cellReferences: (columnId: string, value: string | null) => FetchReference[]
  /** The ways back drawn in this cell, for this row. */
  cellArriving: (columnId: string, value: string | null) => ArrivingReference[]
  follow: (values: readonly (string | null)[], reference: FetchReference) => Promise<void>
  followBack: (
    values: readonly (string | null)[],
    reference: ArrivingReference
  ) => Promise<void>
  /** Whether a jump is under way; both marks give way to it. */
  isPending: Ref<boolean>
}

export function useReferences(options: {
  connectorId: Ref<string>
  nodeId: Ref<string>
  /** The page's columns, in the order its values are in. */
  columns: Ref<readonly FetchColumn[]>
  /** The columns on screen, which decides where a handle sits. */
  visible: Ref<readonly string[]>
  /** The keys of this relation, as the page reported them. */
  references: Ref<readonly FetchReference[]>
  onFollow: (target: ReferencedRows) => void
}): RowReferences {
  const toast = useToast()
  const followReference = useFollowReference(options.connectorId)
  const arriving = useArrivingReferences(options.connectorId, options.nodeId)

  // Worked out once per answer rather than once per cell: a template asks
  // about every cell of every row on every render, and a page runs to five
  // hundred rows.
  const ledBy = <T extends { name: string; columns: string[] }>(
    found: readonly T[]
  ): Map<string, T[]> => {
    const visible = [...options.visible.value]
    const byColumn = new Map<string, T[]>()
    for (const id of visible) {
      const led = referencesLedBy(found, id, visible)
      if (led.length > 0) byColumn.set(id, led)
    }
    return byColumn
  }

  const referencesByColumn = computed(() => ledBy(options.references.value))
  const arrivingByColumn = computed(() => ledBy(arriving.data.value ?? []))

  /**
   * A cell with nothing in it draws none: an empty cell has no value to act
   * on, which is the same reason a null one does not open the viewer. Whether
   * an incomplete key names a row is not decided here — the source answers
   * that when the mark is actually pressed.
   */
  function cellReferences(columnId: string, value: string | null): FetchReference[] {
    if (value === null) return NO_REFERENCES
    return referencesByColumn.value.get(columnId) ?? NO_REFERENCES
  }

  function cellArriving(columnId: string, value: string | null): ArrivingReference[] {
    if (value === null) return NO_ARRIVING
    return arrivingByColumn.value.get(columnId) ?? NO_ARRIVING
  }

  async function jump(
    values: readonly (string | null)[],
    reference: FetchReference | ArrivingReference,
    direction: "outgoing" | "incoming"
  ) {
    const taken = keyValues(reference, options.columns.value, values)
    if (taken === null) {
      toast.info(t("grid.references.stale"))
      return
    }
    try {
      const target = await followReference.mutateAsync({
        node_id: options.nodeId.value,
        reference: reference.name,
        direction,
        values: taken,
      })
      // The source answered that the key names nothing. Not a failure: an
      // empty key is a fact about the row, and it says so in its own words.
      if (target.kind === "none") {
        toast.info(target.reason)
        return
      }
      options.onFollow(target)
    } catch (error) {
      toast.error(messageOf(error, t("grid.references.follow_failed")))
    }
  }

  return {
    cellReferences,
    cellArriving,
    follow: (values, reference) => jump(values, reference, "outgoing"),
    followBack: (values, reference) => jump(values, reference, "incoming"),
    isPending: computed(() => followReference.isPending.value),
  }
}
