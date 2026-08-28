<script setup lang="ts">
import { computed, ref, toRef } from "vue"

import {
  useAddColumn,
  useColumnDefault,
  useDropColumn,
  useRelationModel,
  useRenameColumn,
} from "@/features/structure/api"
import { badgesFor, foreignKeyLabel } from "@/features/structure/model"
import type { ForeignKey } from "@/features/structure/model"
import { messageOf } from "@/shared/api/errors"
import {
  AppBadge,
  AppBanner,
  AppButton,
  AppEmptyState,
  AppIconButton,
  AppSection,
  AppSpinner,
  AppTable,
  AppTooltip,
  useConfirm,
  useToast,
} from "@/shared/ui"

import AddColumnDialog from "./AddColumnDialog.vue"
import ColumnDefaultDialog from "./ColumnDefaultDialog.vue"
import RenameColumnDialog from "./RenameColumnDialog.vue"

const props = defineProps<{ connectorId: string; nodeId: string }>()
const connectorId = toRef(props, "connectorId")
const nodeId = toRef(props, "nodeId")
const query = useRelationModel(connectorId, nodeId)
const addColumn = useAddColumn(connectorId, nodeId)
const dropColumn = useDropColumn(connectorId, nodeId)
const renameColumn = useRenameColumn(connectorId, nodeId)
const columnDefault = useColumnDefault(connectorId, nodeId)
const confirm = useConfirm()
const toast = useToast()
const addOpen = ref(false)
const addError = ref("")
const dropping = ref<string | null>(null)
const renaming = ref<string | null>(null)
const renameError = ref("")
const defaultColumn = ref<{ name: string; currentDefault: string | null } | null>(null)
const defaultError = ref("")

defineExpose({ reload: async () => void (await query.refetch()) })

const COLUMNS = [
  { name: "name", label: "Column", field: "name", align: "left" as const },
  { name: "type", label: "Type", field: "type", align: "left" as const },
  { name: "nullable", label: "Null", field: "nullable", align: "left" as const },
  { name: "default", label: "Default", field: "default", align: "left" as const },
  { name: "keys", label: "Keys", field: "keys", align: "left" as const },
  { name: "actions", label: "", field: "actions", align: "right" as const },
]

const rows = computed(() =>
  (query.data.value?.columns ?? []).map((column) => ({
    name: column.name,
    type: column.type.sql,
    nullable: column.nullable ? "yes" : "no",
    default: column.generated ?? column.default ?? "",
    currentDefault: column.default ?? null,
    generated: column.generated !== null && column.generated !== undefined,
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

function openAdd() {
  addError.value = ""
  addOpen.value = true
}

async function saveAdd(value: { name: string; typeCode: string; nullable: boolean }) {
  addError.value = ""
  try {
    await addColumn.mutateAsync({
      node_id: props.nodeId,
      name: value.name,
      type_code: value.typeCode,
      nullable: value.nullable,
    })
    addOpen.value = false
    toast.success(`Column ${value.name} added`)
  } catch (error) {
    addError.value = messageOf(error, "Could not add the column")
  }
}

async function drop(name: string) {
  const accepted = await confirm({
    title: `Drop column ${name}?`,
    message: "Its data and indexes or constraints owned by this column will be removed.",
    confirmLabel: "Drop",
    danger: true,
  })
  if (!accepted) return
  dropping.value = name
  try {
    await dropColumn.mutateAsync({ node_id: props.nodeId, name })
    toast.success(`Column ${name} dropped`)
  } catch (error) {
    toast.error(messageOf(error, "Could not drop the column"))
  } finally {
    dropping.value = null
  }
}

function openRename(name: string) {
  renameError.value = ""
  renaming.value = name
}

async function saveRename(newName: string) {
  const name = renaming.value
  if (name === null) return
  renameError.value = ""
  try {
    await renameColumn.mutateAsync({ node_id: props.nodeId, name, new_name: newName })
    renaming.value = null
    toast.success(`Column ${name} renamed to ${newName}`)
  } catch (error) {
    renameError.value = messageOf(error, "Could not rename the column")
  }
}

function openDefault(name: string, currentDefault: string | null) {
  defaultError.value = ""
  defaultColumn.value = { name, currentDefault }
}

async function changeDefault(action: "set" | "drop", value?: string) {
  const column = defaultColumn.value
  if (column === null) return
  defaultError.value = ""
  try {
    await columnDefault.mutateAsync({
      node_id: props.nodeId,
      name: column.name,
      action,
      ...(action === "set" ? { value: value ?? "" } : {}),
    })
    defaultColumn.value = null
    toast.success(action === "set" ? `Default for ${column.name} set` : `Default for ${column.name} dropped`)
  } catch (error) {
    defaultError.value = messageOf(error, "Could not change the default")
  }
}
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
        <div class="structure-view__heading">
          <div class="structure-view__title">
            Columns
          </div>
          <span :title="query.data.value.column_changes_supported ? undefined : query.data.value.column_changes_reason ?? undefined">
            <AppButton
              label="Add column"
              variant="secondary"
              size="sm"
              :disable="query.data.value.column_changes_supported !== true"
              data-testid="structure-add-column"
              @click="openAdd"
            />
            <AppTooltip v-if="query.data.value.column_changes_supported !== true && query.data.value.column_changes_reason">
              {{ query.data.value.column_changes_reason }}
            </AppTooltip>
          </span>
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
          <template #body-cell-actions="cellProps">
            <q-td :props="cellProps">
              <AppIconButton
                icon="data_object"
                :tooltip="cellProps.row.generated ? 'A generated column cannot have a default' : `Change default for ${cellProps.row.name}`"
                :disable="query.data.value?.column_changes_supported !== true || cellProps.row.generated"
                :data-testid="`structure-default-${cellProps.row.name}`"
                @click="openDefault(String(cellProps.row.name), cellProps.row.currentDefault)"
              />
              <AppIconButton
                icon="edit"
                :tooltip="query.data.value?.column_changes_supported === true ? `Rename column ${cellProps.row.name}` : query.data.value?.column_changes_reason ?? 'This column cannot be renamed'"
                :disable="query.data.value?.column_changes_supported !== true"
                :data-testid="`structure-rename-${cellProps.row.name}`"
                @click="openRename(String(cellProps.row.name))"
              />
              <AppIconButton
                icon="delete_outline"
                :tooltip="query.data.value?.column_changes_supported === true ? `Drop column ${cellProps.row.name}` : query.data.value?.column_changes_reason ?? 'This column cannot be dropped'"
                variant="danger-quiet"
                :disable="query.data.value?.column_changes_supported !== true"
                :loading="dropping === cellProps.row.name"
                :data-testid="`structure-drop-${cellProps.row.name}`"
                @click="drop(String(cellProps.row.name))"
              />
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

    <AddColumnDialog
      v-if="addOpen"
      :model-value="true"
      :types="query.data.value?.column_type_options ?? []"
      :saving="addColumn.isPending.value"
      :error="addError"
      @save="saveAdd"
      @update:model-value="addOpen = false"
    />
    <RenameColumnDialog
      v-if="renaming !== null"
      :model-value="true"
      :name="renaming"
      :saving="renameColumn.isPending.value"
      :error="renameError"
      @save="saveRename"
      @update:model-value="renaming = null"
    />
    <ColumnDefaultDialog
      v-if="defaultColumn !== null"
      :model-value="true"
      :name="defaultColumn.name"
      :current-default="defaultColumn.currentDefault"
      :saving="columnDefault.isPending.value"
      :error="defaultError"
      @save="changeDefault('set', $event)"
      @drop="changeDefault('drop')"
      @update:model-value="defaultColumn = null"
    />
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
.structure-view__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.structure-view__heading .structure-view__title {
  margin-bottom: 0;
}
.structure-view__list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
}
</style>
