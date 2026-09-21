<script setup lang="ts">
import { computed } from "vue"

import type { PlanProblem } from "@/client"

import { useDesign } from "./design"
import type { DraftSection } from "./draft"

const props = defineProps<{
  designId: string
  section: DraftSection
  selected: string
  problems: PlanProblem[]
}>()
const emit = defineEmits<{ select: [section: DraftSection, objectId: string] }>()
const { draft } = useDesign(props.designId)
const troubled = computed(() => new Set(props.problems.map((problem) => problem.object_id)))
const groups = computed(() => [
  {
    section: "columns" as const,
    title: "Columns",
    icon: "view_column",
    count: draft.columns.length,
    rows: draft.columns.map((column) => ({ id: column.id, label: column.name || "(unnamed)" })),
  },
  {
    section: "indexes" as const,
    title: "Indexes",
    icon: "filter_list",
    count: draft.indexes.length,
    rows: draft.indexes.map((index) => ({
      id: index.id,
      label: index.name || "Automatic index name",
    })),
  },
  {
    section: "foreign-keys" as const,
    title: "Foreign keys",
    icon: "link",
    count: draft.foreignKeys.length,
    rows: draft.foreignKeys.map((foreign) => ({
      id: foreign.id,
      label: foreign.name || "Automatic constraint name",
    })),
  },
  {
    section: "constraints" as const,
    title: "Constraints",
    icon: "verified_user",
    count: Number(draft.primaryKey.length > 0) + draft.uniques.length + draft.checks.length,
    rows: [{ id: "constraints", label: "Primary / unique / checks" }],
  },
  {
    section: "options" as const,
    title: "Options",
    icon: "tune",
    count: null,
    rows: [{ id: "options", label: "Storage & partitioning" }],
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
      <button
        type="button"
        class="navigation__header"
        :data-testid="`section-${group.section}`"
        @click="emit('select', group.section, group.rows[0]?.id ?? '')"
      >
        <span>{{ group.title }}</span><span>{{ group.count }}</span>
      </button>
      <button
        v-for="row in group.rows"
        :key="row.id"
        type="button"
        class="navigation__row"
        :class="{ 'navigation__row--wrong': troubled.has(row.id) }"
        :aria-current="
          section === group.section && (selected === row.id || group.section === 'constraints')
        "
        :data-testid="`object-${row.id}`"
        @click="emit('select', group.section, row.id)"
      >
        <q-icon
          :name="group.icon"
          aria-hidden="true"
        />
        <span>{{ row.label }}</span>
      </button>
    </section>
  </nav>
</template>

<style scoped>
.navigation {
  min-width: 0;
  padding: var(--dp-space-2);
  background: var(--dp-chrome-raised);
  border-right: 1px solid var(--dp-border);
}
.navigation__header {
  display: flex;
  justify-content: space-between;
  gap: var(--dp-space-2);
  width: 100%;
  border: 0;
  padding: var(--dp-space-2) var(--dp-space-2) var(--dp-space-half);
  background: transparent;
  color: var(--dp-text-muted);
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  cursor: pointer;
}
.navigation__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  width: 100%;
  padding: var(--dp-space-2) var(--dp-space-2);
  border: 0;
  border-radius: var(--dp-radius-control);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.navigation__row span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.navigation__row:hover {
  background: var(--dp-hover);
}
.navigation__row[aria-current="true"] {
  background: var(--dp-active);
  color: inherit;
}
.navigation__row--wrong {
  text-decoration: underline wavy var(--dp-content-error);
}
.navigation button:focus-visible {
  outline: 2px solid var(--dp-link);
  outline-offset: -2px;
}
@container table-designer (max-width: 560px) {
  .navigation {
    display: flex;
    flex-wrap: wrap;
    gap: var(--dp-space-1);
    border-right: 0;
    border-bottom: 1px solid var(--dp-border);
  }
  .navigation__group {
    display: contents;
  }
  .navigation__header {
    width: 100%;
  }
  .navigation__row {
    width: auto;
    max-width: 100%;
  }
}
</style>
