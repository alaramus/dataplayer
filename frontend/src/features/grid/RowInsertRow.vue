<script setup lang="ts">
import { reactive, watch } from "vue"
import type { CSSProperties } from "vue"

import type { FetchColumn, InsertValue } from "@/client"
import { AppIconButton, AppInput, AppSelect } from "@/shared/ui"

export interface InsertGridColumn {
  column: FetchColumn
  pinned: boolean
  style: CSSProperties
}

const props = defineProps<{
  columns: InsertGridColumn[]
  rowNumber: number
  saving: boolean
}>()
const emit = defineEmits<{
  cancel: []
  paste: []
  save: [values: InsertValue[]]
}>()

const included = reactive<Record<string, boolean>>({})
const nulls = reactive<Record<string, boolean>>({})
const drafts = reactive<Record<string, string>>({})

/**
 * Every column this row has been offered, in the order it first appeared.
 *
 * `columns` is only what the grid shows now, and the grid can hide, show or
 * pin one while the row is open. Seeded once per column and never dropped, so
 * a column revealed later still starts from its own rules and a value already
 * typed is still sent rather than quietly discarded.
 */
const known = new Map<string, FetchColumn>()

watch(
  () => props.columns,
  (columns) => {
    for (const { column } of columns) {
      known.set(column.name, column)
      if (column.name in included) continue
      included[column.name] = column.insert_required === true
      nulls[column.name] = false
      drafts[column.name] = column.type.category === "boolean" ? "false" : ""
    }
  },
  { immediate: true }
)

function options(column: FetchColumn) {
  if (column.type.category === "boolean") {
    return [
      { label: "True", value: "true" },
      { label: "False", value: "false" },
    ]
  }
  return column.type.enum_values ?? []
}

function include(column: FetchColumn) {
  if (column.insertable === true) included[column.name] = true
}

function update(column: FetchColumn, value: unknown) {
  included[column.name] = true
  nulls[column.name] = false
  drafts[column.name] = String(value ?? "")
}

function useDefault(column: FetchColumn) {
  included[column.name] = false
  nulls[column.name] = false
  drafts[column.name] = column.type.category === "boolean" ? "false" : ""
}

function toggleNull(column: FetchColumn) {
  included[column.name] = true
  nulls[column.name] = !nulls[column.name]
}

function save() {
  if (props.saving) return
  emit(
    "save",
    [...known.values()].flatMap((column) =>
      column.insertable === true && included[column.name] === true
        ? [
            {
              column: column.name,
              value: nulls[column.name] === true ? null : (drafts[column.name] ?? ""),
            },
          ]
        : []
    )
  )
}

/**
 * Fill the fields from a copied row.
 *
 * Exposed rather than taken as a prop: this is an event that happens once, and
 * a prop holding the last thing pasted would refill the form every time the
 * component re-rendered. A null means the row being copied held nothing there,
 * which is a value like any other and not an instruction to use the default.
 */
function fill(values: { column: string; value: string | null }[]) {
  for (const { column, value } of values) {
    if (known.get(column)?.insertable !== true) continue
    included[column] = true
    nulls[column] = value === null
    drafts[column] = value ?? ""
  }
}

defineExpose({ fill })

function handleKey(event: KeyboardEvent) {
  if (event.key === "Escape" && !props.saving) {
    event.preventDefault()
    emit("cancel")
  } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    save()
  } else if (event.key.toLowerCase() === "v" && (event.ctrlKey || event.metaKey)) {
    // Only when the press did not land in a field: inside one, Ctrl+V is the
    // browser pasting text into that field, which is also what a reader means.
    if ((event.target as HTMLElement | null)?.tagName !== "INPUT") {
      event.preventDefault()
      emit("paste")
    }
  }
}
</script>

<template>
  <tr
    class="row-insert"
    data-testid="grid-insert-row"
    @keydown="handleKey"
  >
    <td class="row-insert__selector">
      <span>{{ rowNumber }}</span>
      <div class="row-insert__actions">
        <AppIconButton
          icon="check"
          tooltip="Insert row"
          compact
          :loading="saving"
          data-testid="grid-insert-save"
          @click="save"
        />
        <AppIconButton
          icon="content_paste"
          tooltip="Fill these fields from a copied row"
          compact
          :disable="saving"
          data-testid="grid-insert-paste"
          @click="emit('paste')"
        />
        <AppIconButton
          icon="close"
          tooltip="Cancel insertion"
          compact
          :disable="saving"
          data-testid="grid-insert-cancel"
          @click="emit('cancel')"
        />
      </div>
    </td>
    <td
      v-for="entry in columns"
      :key="entry.column.name"
      :style="entry.style"
      :class="{
        'row-insert__pinned': entry.pinned,
        'row-insert__unavailable': entry.column.insertable !== true,
      }"
    >
      <span v-if="entry.column.insertable !== true">—</span>
      <div
        v-else
        class="row-insert__editor"
      >
        <AppSelect
          v-if="entry.column.type.category === 'boolean' || entry.column.type.category === 'enum'"
          :model-value="included[entry.column.name] === true ? drafts[entry.column.name] : null"
          :options="options(entry.column)"
          :disable="nulls[entry.column.name] === true || saving"
          compact
          :data-testid="`grid-insert-value-${entry.column.name}`"
          @update:model-value="update(entry.column, $event)"
        />
        <AppInput
          v-else
          :model-value="drafts[entry.column.name] ?? ''"
          :placeholder="
            nulls[entry.column.name] === true
              ? '<null>'
              : included[entry.column.name] === true
                ? ''
                : '<default>'
          "
          :disable="nulls[entry.column.name] === true || saving"
          compact
          :data-testid="`grid-insert-value-${entry.column.name}`"
          @focus="include(entry.column)"
          @update:model-value="update(entry.column, $event)"
        />
        <div class="row-insert__cell-actions">
          <AppIconButton
            v-if="entry.column.insert_required !== true && included[entry.column.name] === true"
            icon="restart_alt"
            :tooltip="`Use the default for ${entry.column.name}`"
            :disable="saving"
            :data-testid="`grid-insert-default-${entry.column.name}`"
            @click="useDefault(entry.column)"
          />
          <AppIconButton
            v-if="entry.column.nullable === true"
            :icon="nulls[entry.column.name] === true ? 'do_not_disturb_on' : 'block'"
            :tooltip="
              nulls[entry.column.name] === true
                ? `Enter a value for ${entry.column.name}`
                : `Set ${entry.column.name} to SQL NULL`
            "
            :disable="saving"
            :data-testid="`grid-insert-null-${entry.column.name}`"
            @click="toggleNull(entry.column)"
          />
        </div>
      </div>
    </td>
  </tr>
</template>

<style scoped>
.row-insert > td {
  position: relative;
  box-sizing: border-box;
  min-width: 0;
  max-width: none;
  padding: 2px 4px;
  border-right: 1px solid var(--dp-border-faint);
  border-bottom: 1px solid var(--dp-border-faint);
  background: var(--dp-selected-quiet);
  text-align: left;
  white-space: nowrap;
}

.row-insert__selector {
  width: 72px;
  min-width: 72px !important;
  max-width: 72px !important;
  padding: 2px !important;
  color: var(--dp-text-muted);
  text-align: center !important;
}

.row-insert__actions,
.row-insert__editor,
.row-insert__cell-actions {
  display: flex;
  align-items: center;
}

/* Three buttons in a column 72 pixels wide. They are compact for that reason,
   and the row is told they may not spill: without it the check and the cross
   were drawn over the column beside them. */
.row-insert__actions {
  justify-content: center;
  overflow: hidden;
}

.row-insert__editor > :first-child {
  flex: 1;
  min-width: 0;
}

.row-insert__cell-actions {
  flex: none;
}

.row-insert__pinned {
  position: sticky !important;
  z-index: var(--dp-layer-sticky);
  background: var(--dp-selected-quiet) !important;
  box-shadow: 2px 0 3px var(--dp-shadow-soft);
}

.row-insert__unavailable {
  color: var(--dp-text-muted);
}
</style>
