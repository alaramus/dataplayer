<script setup lang="ts">
import { computed, ref, toRef, watch } from "vue"

import type { FetchRequest, ReferencedRows } from "@/client"
import { useRowsPage } from "@/features/grid/api"
import { cellPresentation } from "@/features/grid/model"
import { useReferences } from "@/features/grid/useReferences"
import { useRelationModel } from "@/features/structure/api"
import { badgesFor } from "@/features/structure/model"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import {
  AppBadge,
  AppBanner,
  AppButton,
  AppEmptyState,
  AppIconButton,
  AppMenu,
  AppSpinner,
  AppTable,
  AppTooltip,
  useToast,
} from "@/shared/ui"

/**
 * One row, read downwards.
 *
 * The same page the grid is reading, asked for by the same key, so opening a
 * row costs nothing and the two stay in step. What it adds is the shape the
 * old application's window had and the grid cannot have: every column of one
 * row on screen at once, with what the source says about each — its type, the
 * keys it takes part in — beside the value.
 *
 * Which row is a position in a page rather than a handle: a handle exists only
 * where the source can version a row (D25), and walking to the next row is a
 * question about the page rather than about identity.
 */
const props = defineProps<{
  connectorId: string
  nodeId: string
  /** Whether the source will describe this relation; badges come from that. */
  describable: boolean
  /**
   * The page the row is in, exactly as the grid asked for it.
   *
   * A tab restored from a layout written before the row travelled with it has
   * none, and comes back on the first row of the relation rather than on
   * nothing at all.
   */
  request?: FetchRequest
  /** Which row of that page, from zero. */
  index: number
}>()

/** What a row view reads when it was not told which page to read. */
function firstPage(nodeId: string): FetchRequest {
  return { node_id: nodeId, limit: 100, offset: 0, filters: [], sort: [] }
}
const emit = defineEmits<{ follow: [target: ReferencedRows] }>()

const toast = useToast()
const request = ref<FetchRequest>({ ...(props.request ?? firstPage(props.nodeId)) })
const index = ref(props.index)

watch(
  () => [props.request, props.index] as const,
  ([asked, at]) => {
    request.value = { ...(asked ?? firstPage(props.nodeId)) }
    index.value = at
  }
)

const page = useRowsPage(
  toRef(props, "connectorId"),
  computed(() => request.value)
)
const result = computed(() => page.data.value?.page)
const columns = computed(() => result.value?.columns ?? [])
const values = computed(() => result.value?.rows[index.value] ?? null)

const model = useRelationModel(
  toRef(props, "connectorId"),
  toRef(props, "nodeId"),
  computed(() => props.describable)
)

const { cellReferences, cellArriving, follow, followBack, isPending: jumping } =
  useReferences({
    connectorId: toRef(props, "connectorId"),
    nodeId: toRef(props, "nodeId"),
    columns,
    // Everything is on screen here: a row read downwards hides nothing, so a
    // key's handle always sits on the first of its columns.
    visible: computed(() => columns.value.map((column) => column.name)),
    references: computed(() => result.value?.references ?? []),
    onFollow: (target) => emit("follow", target),
  })

const COLUMNS = [
  { name: "keys", label: "Key", field: "keys", align: "left" as const },
  { name: "name", label: "Column", field: "name", align: "left" as const },
  { name: "type", label: "Type", field: "type", align: "left" as const },
  { name: "value", label: "Value", field: "value", align: "left" as const },
]

interface Line {
  name: string
  type: string
  value: string | null
  text: string
  absent: boolean
  monospace: boolean
  keys: { kind: string; label: string; tooltip?: string | null }[]
}

const lines = computed<Line[]>(() => {
  const held = values.value
  if (held === null) return []
  const described = props.describable ? model.data.value : undefined
  return columns.value.map((column, at) => {
    const value = held[at] ?? null
    const shown = cellPresentation(value, column.type)
    return {
      name: column.name,
      type: column.type.sql,
      value,
      text: shown.text,
      // The absence of a value is drawn as an absence, not as the word: the
      // grid draws it the same way and for the same reason.
      absent: value === null,
      monospace: shown.monospace === true,
      keys: described === undefined ? [] : badgesFor(described, column.name),
    }
  })
})

/** Where this row sits in the whole relation, counting from one. */
const number = computed(() => (request.value.offset ?? 0) + index.value + 1)
const limit = computed(() => request.value.limit ?? 100)
const hasPrevious = computed(() => index.value > 0 || (request.value.offset ?? 0) > 0)
const hasNext = computed(
  () =>
    index.value + 1 < (result.value?.rows.length ?? 0) ||
    result.value?.has_more === true
)

/**
 * Walking rows crosses pages, because a page is how the source hands them
 * over and not something a reader should have to know about. The page moves
 * by exactly what it was asked for, so the request stays one the grid also
 * uses and the answer is one both of them share.
 */
function step(by: 1 | -1) {
  const rows = result.value?.rows.length ?? 0
  const next = index.value + by
  if (next >= 0 && next < rows) {
    index.value = next
    return
  }
  const offset = request.value.offset ?? 0
  if (by === -1) {
    if (offset === 0) return
    const back = Math.max(0, offset - limit.value)
    request.value = { ...request.value, offset: back }
    index.value = Math.min(limit.value, offset - back) - 1
    return
  }
  if (result.value?.has_more !== true) return
  request.value = { ...request.value, offset: offset + limit.value }
  index.value = 0
}

async function copy(line: Line) {
  await copyText(line.value ?? "")
  toast.success(`${line.name} copied`)
}

const errorText = computed(() =>
  page.isError.value
    ? messageOf(page.error.value, "Could not read this row")
    : ""
)
</script>

<template>
  <div
    class="record-view"
    data-testid="record-view"
  >
    <AppBanner
      v-if="errorText"
      tone="error"
      data-testid="record-error"
    >
      {{ errorText }}
    </AppBanner>

    <AppSpinner v-else-if="page.isPending.value" />

    <template v-else>
      <div class="record-view__bar">
        <AppButton
          label="Previous"
          variant="secondary"
          size="sm"
          icon="chevron_left"
          :disable="!hasPrevious"
          data-testid="record-previous"
          @click="step(-1)"
        />
        <span
          class="record-view__where"
          data-testid="record-number"
        >Row {{ number }}</span>
        <AppButton
          label="Next"
          variant="secondary"
          size="sm"
          icon-right="chevron_right"
          :disable="!hasNext"
          data-testid="record-next"
          @click="step(1)"
        />
      </div>

      <AppEmptyState
        v-if="lines.length === 0"
        text="No row here"
        data-testid="record-empty"
      />
      <AppTable
        v-else
        :rows="lines"
        :columns="COLUMNS"
        row-key="name"
        compact
        :paged="false"
        empty-text="No columns"
      >
        <template #body-cell-keys="cellProps">
          <q-td :props="cellProps">
            <span
              v-for="badge in cellProps.value"
              :key="badge.kind"
            >
              <AppBadge
                :label="badge.label"
                :data-testid="`record-badge-${badge.kind}`"
              />
              <AppTooltip v-if="badge.tooltip">{{ badge.tooltip }}</AppTooltip>
            </span>
          </q-td>
        </template>
        <template #body-cell-value="cellProps">
          <q-td :props="cellProps">
            <div class="record-view__value">
              <span
                :class="{
                  'record-view__null': cellProps.row.absent,
                  'record-view__monospace': cellProps.row.monospace,
                }"
                :data-testid="`record-value-${cellProps.row.name}`"
              >{{ cellProps.row.text }}</span>
              <span class="record-view__ways">
                <AppIconButton
                  v-for="reference in cellReferences(cellProps.row.name, cellProps.row.value)"
                  :key="reference.name"
                  icon="arrow_forward"
                  compact
                  :tooltip="`Go to ${reference.target_title}`"
                  :disable="jumping"
                  :data-testid="`record-follow-${cellProps.row.name}`"
                  @click="follow(values ?? [], reference)"
                />
                <span
                  v-if="cellArriving(cellProps.row.name, cellProps.row.value).length > 0"
                >
                  <AppIconButton
                    icon="arrow_back"
                    compact
                    tooltip="What points at this row"
                    :disable="jumping"
                    :data-testid="`record-arriving-${cellProps.row.name}`"
                  />
                  <AppMenu
                    :items="
                      cellArriving(cellProps.row.name, cellProps.row.value).map(
                        (reference) => ({
                          name: reference.name,
                          label: reference.source_title,
                        })
                      )
                    "
                    @select="
                      (name) =>
                        followBack(
                          values ?? [],
                          cellArriving(cellProps.row.name, cellProps.row.value).find(
                            (reference) => reference.name === name
                          )!
                        )
                    "
                  />
                </span>
                <AppIconButton
                  icon="content_copy"
                  compact
                  tooltip="Copy this value"
                  :data-testid="`record-copy-${cellProps.row.name}`"
                  @click="copy(cellProps.row)"
                />
              </span>
            </div>
          </q-td>
        </template>
      </AppTable>
    </template>
  </div>
</template>

<style scoped>
.record-view {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: auto;
}
.record-view__bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
}
.record-view__where {
  font-weight: 600;
}
.record-view__value {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}
.record-view__ways {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: none;
}
.record-view__null {
  color: var(--dp-text-muted);
  font-style: italic;
}
.record-view__monospace {
  font-family: monospace;
}
</style>
