<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import type { PlanProblem } from "@/client"
import { t } from "@/shared/i18n"

import { useDesign } from "./design"
import type { DraftSection } from "./draft"

const props = defineProps<{
  designId: string
  section: DraftSection
  selected: string
  problems: PlanProblem[]
}>()
const emit = defineEmits<{ select: [section: DraftSection, objectId: string] }>()
const { draft, options } = useDesign(props.designId)
const troubled = computed(() => new Set(props.problems.map((problem) => problem.object_id)))
const groups = computed(() => [
  {
    section: "columns" as const,
    title: t("table_design.designer.headings.columns"),
    icon: appIcons.viewColumn,
    count: draft.columns.length,
    rows: draft.columns.map((column) => ({ id: column.id, label: column.name || t("table_design.unnamed") })),
  },
  {
    section: "indexes" as const,
    title: t("table_design.designer.headings.indexes"),
    icon: appIcons.filterList,
    count: draft.indexes.length,
    rows: draft.indexes.map((index) => ({
      id: index.id,
      label: index.name || t("table_design.automatic_index_name"),
    })),
  },
  {
    section: "foreign-keys" as const,
    title: t("table_design.designer.headings.foreign_keys"),
    icon: appIcons.link,
    count: draft.foreignKeys.length,
    rows: draft.foreignKeys.map((foreign) => ({
      id: foreign.id,
      label: foreign.name || t("table_design.automatic_constraint_name"),
    })),
  },
  {
    section: "constraints" as const,
    title: t("table_design.designer.headings.constraints"),
    icon: appIcons.verifiedUser,
    count: Number(draft.primaryKey.length > 0) + draft.uniques.length + draft.checks.length,
    rows: [{ id: "constraints", label: t("table_design.navigation.constraints_row") }],
  },
  {
    section: "options" as const,
    title: t("table_design.navigation.options"),
    icon: appIcons.preferences,
    count: null,
    rows: [
      { id: "options", label: t("table_design.navigation.storage") },
      // The only section the server may lack: a database without TimescaleDB
      // says so in it, and a source with no hypertables at all leaves it out.
      ...(options.value?.hypertable?.offered === false
        ? []
        : [{ id: "hypertable", label: draft.hypertable ? t("table_design.navigation.hypertable") : t("table_design.navigation.hypertable_off") }]),
    ],
  },
])
</script>

<template>
  <nav
    class="navigation"
    :aria-label="t('table_design.navigation.aria')"
    data-testid="design-navigation"
  >
    <section
      v-for="group in groups"
      :key="group.section"
      class="navigation__group"
    >
      <button
        type="button"
        class="navigation__header dp-overline"
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
          size="var(--dp-icon-sm)"
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
  min-height: 0;
  overflow-y: auto;
  padding: var(--dp-space-2);
  background: var(--dp-chrome-raised);
  border-right: 1px solid var(--dp-border);
}
/* Trap: `font: inherit` here undid the overline it carries — the headings
   stood at the body's 13px and 400 in capitals, an overline of their own. */
.navigation__header {
  display: flex;
  justify-content: space-between;
  gap: var(--dp-space-2);
  width: 100%;
  border: 0;
  padding: var(--dp-space-2) var(--dp-space-2) var(--dp-space-half);
  background: transparent;
  font-family: inherit;
  cursor: pointer;
}
.navigation__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  width: 100%;
  min-height: var(--dp-row-height);
  padding: var(--dp-space-1) var(--dp-space-2);
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
  background: var(--dp-tab-current);
  color: inherit;
  font-weight: 500;
}
.navigation__row--wrong {
  text-decoration: underline wavy var(--dp-content-error);
}
.navigation button:focus-visible {
  outline: 2px solid var(--dp-focus-border);
  outline-offset: -2px;
}
@container table-designer (max-width: 850px) {
  .navigation {
    overflow-y: visible;
  }
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
