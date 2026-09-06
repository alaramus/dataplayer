<script setup lang="ts">
import { computed } from "vue"

import type { PlanProblem } from "@/client"
import { AppIconButton, AppTooltip } from "@/shared/ui"

import { useDesign } from "./design"
import type { DraftSection } from "./draft"

/**
 * The objects of the table, as a list that is also the way around it.
 *
 * The selection lives in the window rather than here: two panes show it, and a
 * component that owned it would be telling its parent what is on screen.
 */
const props = defineProps<{
  designId: string
  section: DraftSection
  selected: string
  problems: PlanProblem[]
}>()

const emit = defineEmits<{
  select: [section: DraftSection, objectId: string]
  add: [section: DraftSection]
  remove: [section: DraftSection, objectId: string]
}>()

const design = useDesign(props.designId)

interface Row {
  id: string
  label: string
  note: string
}

const troubled = computed(
  () => new Set(props.problems.flatMap((problem) => (problem.object_id === null || problem.object_id === undefined ? [] : [problem.object_id])))
)

const columns = computed<Row[]>(() =>
  design.draft.columns.map((column) => ({
    id: column.id,
    label: column.name || "(unnamed)",
    note: design.draft.primaryKey.includes(column.id) ? "key" : "",
  }))
)
const indexes = computed<Row[]>(() =>
  design.draft.indexes.map((index) => ({
    id: index.id,
    label: index.name || "(named by the database)",
    note: index.unique ? `${index.method} · unique` : index.method,
  }))
)
const foreignKeys = computed<Row[]>(() =>
  design.draft.foreignKeys.map((foreign) => ({
    id: foreign.id,
    label: foreign.name || "(named by the database)",
    note: foreign.targetLabel,
  }))
)
const constraints = computed<Row[]>(() => [
  ...design.draft.uniques.map((unique) => ({
    id: unique.id,
    label: unique.name || "(named by the database)",
    note: "unique",
  })),
  ...design.draft.checks.map((check) => ({
    id: check.id,
    label: check.name || "(named by the database)",
    note: "check",
  })),
])

const groups = computed(() => [
  { section: "columns" as const, title: "Columns", rows: columns.value, adds: "Add a column" },
  { section: "indexes" as const, title: "Indexes", rows: indexes.value, adds: "Add an index" },
  {
    section: "foreign-keys" as const,
    title: "Foreign keys",
    rows: foreignKeys.value,
    adds: "Add a foreign key",
  },
  {
    section: "constraints" as const,
    title: "Constraints",
    rows: constraints.value,
    adds: "Add a check",
  },
])
</script>

<template>
  <nav
    class="navigation"
    aria-label="Table definition"
    data-testid="design-navigation"
  >
    <section
      v-for="group in groups"
      :key="group.section"
      class="navigation__group"
    >
      <header class="navigation__header">
        <span>{{ group.title }}</span>
        <span class="navigation__count">{{ group.rows.length }}</span>
        <AppIconButton
          icon="add"
          :tooltip="group.adds"
          compact
          :data-testid="`add-${group.section}`"
          @click="emit('add', group.section)"
        />
      </header>
      <button
        v-for="row in group.rows"
        :key="row.id"
        type="button"
        class="navigation__row"
        :class="{
          'navigation__row--on': section === group.section && selected === row.id,
          'navigation__row--wrong': troubled.has(row.id),
        }"
        :data-testid="`object-${row.id}`"
        @click="emit('select', group.section, row.id)"
      >
        <span class="navigation__label">{{ row.label }}</span>
        <span
          v-if="row.note"
          class="navigation__note"
        >{{ row.note }}</span>
        <AppTooltip v-if="row.label.length > 24">
          {{ row.label }}
        </AppTooltip>
      </button>
      <p
        v-if="group.rows.length === 0"
        class="navigation__empty"
      >
        None yet
      </p>
    </section>

    <button
      type="button"
      class="navigation__row navigation__row--single"
      :class="{ 'navigation__row--on': section === 'options' }"
      data-testid="object-options"
      @click="emit('select', 'options', '')"
    >
      <span class="navigation__label">Table options</span>
    </button>

    <div class="navigation__foot">
      <AppIconButton
        v-if="section !== 'options' && selected !== ''"
        icon="delete_outline"
        variant="danger-quiet"
        tooltip="Remove the selected object"
        compact
        data-testid="remove-object"
        @click="emit('remove', section, selected)"
      />
    </div>
  </nav>
</template>

<style scoped>
.navigation {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  overflow: auto;
  padding-right: var(--dp-space-1);
}

.navigation__group {
  display: flex;
  flex-direction: column;
}

.navigation__header {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--dp-text-muted);
  padding: var(--dp-space-1) 0;
}

.navigation__count {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.navigation__row {
  display: flex;
  align-items: baseline;
  gap: var(--dp-space-1);
  width: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  padding: 3px var(--dp-space-1);
  border-radius: var(--dp-radius-control);
  cursor: pointer;
}

.navigation__row:hover {
  background: var(--dp-hover);
}

.navigation__row--on {
  background: var(--dp-selected);
}

/* A name too long for the pane is clipped rather than allowed to widen it:
   the inspector beside it is what has room, and the tooltip says the rest. */
.navigation__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.navigation__note {
  margin-left: auto;
  font-size: 11px;
  color: var(--dp-text-faint);
  white-space: nowrap;
}

.navigation__row--wrong .navigation__label {
  text-decoration: underline wavy var(--q-negative);
}

.navigation__row--single {
  margin-top: auto;
}

.navigation__empty {
  margin: 0;
  padding: 2px var(--dp-space-1);
  font-size: 11px;
  color: var(--dp-text-faint);
}

.navigation__foot {
  display: flex;
  justify-content: flex-end;
  min-height: 24px;
}
</style>
