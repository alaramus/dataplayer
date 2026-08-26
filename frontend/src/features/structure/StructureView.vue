<script setup lang="ts">
import { computed, toRef } from "vue"

import { useRelationModel } from "@/features/structure/api"
import { badgesFor, foreignKeyLabel } from "@/features/structure/model"
import type { ForeignKey } from "@/features/structure/model"
import { messageOf } from "@/shared/api/errors"
import {
  AppBadge,
  AppBanner,
  AppEmptyState,
  AppSection,
  AppSpinner,
  AppTable,
  AppTooltip,
} from "@/shared/ui"

const props = defineProps<{ connectorId: string; nodeId: string }>()
const query = useRelationModel(toRef(props, "connectorId"), toRef(props, "nodeId"))

defineExpose({ reload: async () => void (await query.refetch()) })

const COLUMNS = [
  { name: "name", label: "Column", field: "name", align: "left" as const },
  { name: "type", label: "Type", field: "type", align: "left" as const },
  { name: "nullable", label: "Null", field: "nullable", align: "left" as const },
  { name: "default", label: "Default", field: "default", align: "left" as const },
  { name: "keys", label: "Keys", field: "keys", align: "left" as const },
]

const rows = computed(() =>
  (query.data.value?.columns ?? []).map((column) => ({
    name: column.name,
    type: column.type.sql,
    nullable: column.nullable ? "yes" : "no",
    default: column.generated ?? column.default ?? "",
    keys: query.data.value === undefined ? [] : badgesFor(query.data.value, column.name),
  }))
)

const foreignKeys = computed(
  () =>
    (query.data.value?.constraints ?? []).filter(
      (constraint) => constraint.kind === "foreign_key"
    ) as ForeignKey[]
)
const otherConstraints = computed(() =>
  (query.data.value?.constraints ?? []).filter(
    (constraint) => constraint.kind !== "foreign_key"
  )
)
const errorText = computed(() =>
  query.error.value === null
    ? ""
    : messageOf(query.error.value, "Could not read the structure")
)
</script>

<template>
  <div
    class="structure-view"
    data-testid="structure-view"
  >
    <AppBanner
      v-if="errorText"
      tone="error"
      data-testid="structure-error"
    >
      {{ errorText }}
    </AppBanner>

    <AppSpinner v-else-if="query.isPending.value" />

    <template v-else-if="query.data.value">
      <AppSection>
        <div class="structure-view__title">
          Columns
        </div>
        <AppTable
          :rows="rows"
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
                  :data-testid="`structure-badge-${badge.kind}`"
                />
                <AppTooltip>{{ badge.tooltip }}</AppTooltip>
              </span>
            </q-td>
          </template>
        </AppTable>
      </AppSection>

      <AppSection divided>
        <div class="structure-view__title">
          Foreign keys
        </div>
        <AppEmptyState
          v-if="foreignKeys.length === 0"
          text="None"
        />
        <ul
          v-else
          class="structure-view__list"
        >
          <li
            v-for="key in foreignKeys"
            :key="key.name"
            data-testid="structure-fk"
          >
            {{ foreignKeyLabel(key) }}
          </li>
        </ul>
      </AppSection>

      <AppSection divided>
        <div class="structure-view__title">
          Constraints
        </div>
        <AppEmptyState
          v-if="otherConstraints.length === 0"
          text="None"
        />
        <ul
          v-else
          class="structure-view__list"
        >
          <li
            v-for="constraint in otherConstraints"
            :key="constraint.name"
          >
            {{ constraint.kind }} · {{ constraint.name }}
          </li>
        </ul>
      </AppSection>

      <AppSection divided>
        <div class="structure-view__title">
          Indexes
        </div>
        <AppEmptyState
          v-if="(query.data.value.indexes ?? []).length === 0"
          text="None"
        />
        <ul
          v-else
          class="structure-view__list"
        >
          <li
            v-for="index in query.data.value.indexes ?? []"
            :key="index.name"
          >
            {{ index.name }} · {{ index.method }}
            <template v-if="(index.columns ?? []).length">
              ({{ (index.columns ?? []).join(", ") }})
            </template>
          </li>
        </ul>
      </AppSection>
    </template>
  </div>
</template>

<style scoped>
.structure-view {
  height: 100%;
  min-height: 0;
  overflow: auto;
}
.structure-view__title {
  margin-bottom: 8px;
  font-weight: 600;
}
.structure-view__list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
}
</style>
