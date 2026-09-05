<script setup lang="ts">
import { computed, ref, toRef } from "vue"

import {
  useAddColumn,
  useColumnDefault,
  useColumnNullability,
  useColumnType,
  useCreateConstraint,
  useCreateIndex,
  useDropColumn,
  useDropConstraint,
  useDropIndex,
  useRelationModel,
  useRenameColumn,
} from "@/features/structure/api"
import { badgesFor, datasetFacts, foreignKeyLabel } from "@/features/structure/model"
import type { ForeignKey, RefAction } from "@/features/structure/model"
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

import DeclaredReferencesSection from "@/features/declared/DeclaredReferencesSection.vue"

import AddColumnDialog from "./AddColumnDialog.vue"
import AddConstraintDialog from "./AddConstraintDialog.vue"
import ColumnDefaultDialog from "./ColumnDefaultDialog.vue"
import ColumnNullabilityDialog from "./ColumnNullabilityDialog.vue"
import ColumnTypeDialog from "./ColumnTypeDialog.vue"
import CreateIndexDialog from "./CreateIndexDialog.vue"
import RenameColumnDialog from "./RenameColumnDialog.vue"

const props = defineProps<{ connectorId: string; nodeId: string }>()
const connectorId = toRef(props, "connectorId")
const nodeId = toRef(props, "nodeId")
const query = useRelationModel(connectorId, nodeId)
const addColumn = useAddColumn(connectorId, nodeId)
const dropColumn = useDropColumn(connectorId, nodeId)
const renameColumn = useRenameColumn(connectorId, nodeId)
const columnDefault = useColumnDefault(connectorId, nodeId)
const columnNullability = useColumnNullability(connectorId, nodeId)
const columnType = useColumnType(connectorId, nodeId)
const createIndex = useCreateIndex(connectorId, nodeId)
const dropIndex = useDropIndex(connectorId, nodeId)
const createConstraint = useCreateConstraint(connectorId, nodeId)
const dropConstraint = useDropConstraint(connectorId, nodeId)
const confirm = useConfirm()
const toast = useToast()
const addOpen = ref(false)
const addError = ref("")
const dropping = ref<string | null>(null)
const renaming = ref<string | null>(null)
const renameError = ref("")
const defaultColumn = ref<{ name: string; currentDefault: string | null } | null>(null)
const defaultError = ref("")
const nullabilityColumn = ref<{ name: string; nullable: boolean } | null>(null)
const nullabilityError = ref("")
const nullabilityBlocked = ref<{ rows: number; exact: boolean } | null>(null)
const typeColumn = ref<{ name: string; currentType: string } | null>(null)
const typeError = ref("")
const typeBlocked = ref<{ rows: number; exact: boolean } | null>(null)
const indexOpen = ref(false)
const indexError = ref("")
const indexBlocked = ref<{ groups: number; exact: boolean } | null>(null)
const droppingIndex = ref<string | null>(null)
const constraintOpen = ref(false)
const constraintError = ref("")
const constraintBlocked = ref<{
  kind: "repeating" | "unmatched"
  count: number
  exact: boolean
} | null>(null)
const droppingConstraint = ref<string | null>(null)

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
    nullable: column.nullable,
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
/** The format's own facts, for a relation that is a file (D51). */
const facts = computed(() => {
  const dataset = query.data.value?.dataset
  return dataset === null || dataset === undefined ? [] : datasetFacts(dataset)
})
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

function constraintTooltip(name: string): string {
  const model = query.data.value
  if (model?.constraint_changes_supported !== true) {
    return model?.constraint_changes_reason ?? "This constraint cannot be dropped"
  }
  return `Drop constraint ${name}`
}

type ColumnOperation = "add" | "drop" | "rename" | "default" | "nullability" | "type"

function supportsColumn(operation: ColumnOperation): boolean {
  const model = query.data.value
  if (model?.column_operations !== undefined && model.column_operations.length > 0) {
    return model.column_operations.includes(operation)
  }
  return model?.column_changes_supported === true
}

function changeTooltip(operation: ColumnOperation, what: string): string {
  const model = query.data.value
  if (!supportsColumn(operation)) {
    return model?.column_changes_reason ?? "This column cannot be changed"
  }
  return what
}

function openType(name: string, currentType: string) {
  typeError.value = ""
  typeBlocked.value = null
  typeColumn.value = { name, currentType }
}

async function changeType(typeCode: string) {
  const column = typeColumn.value
  if (column === null) return
  typeError.value = ""
  typeBlocked.value = null
  try {
    const result = await columnType.mutateAsync({
      node_id: props.nodeId,
      name: column.name,
      type_code: typeCode,
    })
    // Not a failure: the source read the values, rewrote nothing and said how
    // many it could not read. The dialog stays open so the number can be read.
    if (result.kind === "blocked") {
      typeBlocked.value = {
        rows: result.rows_not_convertible,
        exact: result.exact ?? true,
      }
      return
    }
    typeColumn.value = null
    toast.success(`${column.name} is now ${result.type_sql}`)
  } catch (error) {
    typeError.value = messageOf(error, "Could not change the type")
  }
}

function openConstraint() {
  constraintError.value = ""
  constraintBlocked.value = null
  constraintOpen.value = true
}

type ConstraintChoice =
  | { kind: "unique"; columns: string[] }
  | {
      kind: "foreign_key"
      columns: string[]
      targetNodeId: string
      targetColumns: string[]
      onUpdate: RefAction
      onDelete: RefAction
    }

async function saveConstraint(value: ConstraintChoice) {
  constraintError.value = ""
  constraintBlocked.value = null
  try {
    const result = await createConstraint.mutateAsync({
      node_id: props.nodeId,
      constraint:
        value.kind === "unique"
          ? { kind: "unique", columns: value.columns }
          : {
              kind: "foreign_key",
              columns: value.columns,
              target_node_id: value.targetNodeId,
              target_columns: value.targetColumns,
              on_update: value.onUpdate,
              on_delete: value.onDelete,
            },
    })
    // Not a failure: the source counted what contradicts the promise and
    // added nothing, so the dialog stays open with the number.
    if (result.kind !== "created") {
      constraintBlocked.value = {
        kind: result.kind,
        count: result.kind === "repeating" ? result.groups : result.rows,
        exact: result.exact ?? true,
      }
      return
    }
    constraintOpen.value = false
    toast.success(`Constraint ${result.name} added`)
  } catch (error) {
    constraintError.value = messageOf(error, "Could not add the constraint")
  }
}

async function removeConstraint(name: string) {
  const accepted = await confirm({
    title: `Drop constraint ${name}?`,
    message: "The promise it makes about the rows stops being enforced.",
    confirmLabel: "Drop",
    danger: true,
  })
  if (!accepted) return
  droppingConstraint.value = name
  try {
    await dropConstraint.mutateAsync({ node_id: props.nodeId, name })
    toast.success(`Constraint ${name} dropped`)
  } catch (error) {
    toast.error(messageOf(error, "Could not drop the constraint"))
  } finally {
    droppingConstraint.value = null
  }
}

function openIndex() {
  indexError.value = ""
  indexBlocked.value = null
  indexOpen.value = true
}

async function saveIndex(value: {
  columns: string[]
  method: string
  unique: boolean
}) {
  indexError.value = ""
  indexBlocked.value = null
  try {
    const result = await createIndex.mutateAsync({
      node_id: props.nodeId,
      columns: value.columns,
      method: value.method,
      unique: value.unique,
    })
    // Not a failure: the source counted the repeats and built nothing, so the
    // dialog stays open with the number.
    if (result.kind === "blocked") {
      indexBlocked.value = {
        groups: result.duplicate_groups,
        exact: result.exact ?? true,
      }
      return
    }
    indexOpen.value = false
    toast.success(`Index ${result.name} created`)
  } catch (error) {
    indexError.value = messageOf(error, "Could not create the index")
  }
}

async function removeIndex(name: string) {
  const accepted = await confirm({
    title: `Drop index ${name}?`,
    message: "Queries that rely on it will be planned without it.",
    confirmLabel: "Drop",
    danger: true,
  })
  if (!accepted) return
  droppingIndex.value = name
  try {
    await dropIndex.mutateAsync({ node_id: props.nodeId, name })
    toast.success(`Index ${name} dropped`)
  } catch (error) {
    toast.error(messageOf(error, "Could not drop the index"))
  } finally {
    droppingIndex.value = null
  }
}

function nullabilityTooltip(nullable: boolean): string {
  return changeTooltip(
    "nullability",
    nullable ? "Require a value in every row" : "Allow rows with no value"
  )
}

function openNullability(name: string, nullable: boolean) {
  nullabilityError.value = ""
  nullabilityBlocked.value = null
  nullabilityColumn.value = { name, nullable }
}

async function changeNullability(nullable: boolean) {
  const column = nullabilityColumn.value
  if (column === null) return
  nullabilityError.value = ""
  nullabilityBlocked.value = null
  try {
    const result = await columnNullability.mutateAsync({
      node_id: props.nodeId,
      name: column.name,
      nullable,
    })
    // Not a failure: the source read the rows, changed nothing and said how
    // many stand in the way. The dialog stays open so the number can be read.
    if (result.kind === "blocked") {
      nullabilityBlocked.value = {
        rows: result.rows_without_value,
        exact: result.exact ?? true,
      }
      return
    }
    nullabilityColumn.value = null
    toast.success(
      nullable
        ? `${column.name} now accepts rows with no value`
        : `${column.name} now requires a value`
    )
  } catch (error) {
    nullabilityError.value = messageOf(error, "Could not change this column")
  }
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
      <AppSection
        v-if="facts.length > 0"
        data-testid="structure-format"
      >
        <div class="structure-view__title">
          Format
        </div>
        <dl class="structure-view__facts">
          <template
            v-for="fact in facts"
            :key="fact.label"
          >
            <dt>{{ fact.label }}</dt>
            <dd :data-testid="`structure-fact-${fact.label}`">
              {{ fact.value }}
            </dd>
          </template>
        </dl>
      </AppSection>

      <AppSection :divided="facts.length > 0">
        <div class="structure-view__heading">
          <div class="structure-view__title">
            Columns
          </div>
          <span
            :title="query.data.value.column_changes_supported
              ? undefined
              : query.data.value.column_changes_reason ?? undefined"
          >
            <AppButton
              label="Add column"
              variant="secondary"
              size="sm"
              :disable="!supportsColumn('add')"
              data-testid="structure-add-column"
              @click="openAdd"
            />
            <AppTooltip v-if="!supportsColumn('add') && query.data.value.column_changes_reason">
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
          <!-- The fact being changed is already printed here, so it is the
               control: another icon in the row of actions would have to name
               in a tooltip which of a column's facts it changes. -->
          <template #body-cell-type="cellProps">
            <q-td :props="cellProps">
              <AppButton
                :label="String(cellProps.row.type)"
                variant="quiet"
                size="sm"
                :disable="!supportsColumn('type') || cellProps.row.generated"
                :data-testid="`structure-type-${cellProps.row.name}`"
                @click="openType(String(cellProps.row.name), String(cellProps.row.type))"
              >
                <AppTooltip>
                  {{ cellProps.row.generated
                    ? 'A generated column takes its type from its expression'
                    : changeTooltip('type', `Change the type of ${cellProps.row.name}`) }}
                </AppTooltip>
              </AppButton>
            </q-td>
          </template>
          <template #body-cell-nullable="cellProps">
            <q-td :props="cellProps">
              <AppButton
                :label="cellProps.row.nullable ? 'yes' : 'no'"
                variant="quiet"
                size="sm"
                :disable="!supportsColumn('nullability')"
                :data-testid="`structure-nullability-${cellProps.row.name}`"
                @click="openNullability(String(cellProps.row.name), cellProps.row.nullable)"
              >
                <AppTooltip>{{ nullabilityTooltip(cellProps.row.nullable) }}</AppTooltip>
              </AppButton>
            </q-td>
          </template>
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
                :tooltip="cellProps.row.generated
                  ? 'A generated column cannot have a default'
                  : `Change default for ${cellProps.row.name}`"
                :disable="!supportsColumn('default') || cellProps.row.generated"
                :data-testid="`structure-default-${cellProps.row.name}`"
                @click="openDefault(String(cellProps.row.name), cellProps.row.currentDefault)"
              />
              <AppIconButton
                icon="edit"
                :tooltip="changeTooltip('rename', `Rename column ${cellProps.row.name}`)"
                :disable="!supportsColumn('rename')"
                :data-testid="`structure-rename-${cellProps.row.name}`"
                @click="openRename(String(cellProps.row.name))"
              />
              <AppIconButton
                icon="delete_outline"
                :tooltip="changeTooltip('drop', `Drop column ${cellProps.row.name}`)"
                variant="danger-quiet"
                :disable="!supportsColumn('drop')"
                :loading="dropping === cellProps.row.name"
                :data-testid="`structure-drop-${cellProps.row.name}`"
                @click="drop(String(cellProps.row.name))"
              />
            </q-td>
          </template>
        </AppTable>
      </AppSection>

      <AppSection divided>
        <div class="structure-view__heading">
          <div class="structure-view__title">
            Constraints
          </div>
          <span :title="query.data.value.constraint_changes_supported ? undefined : query.data.value.constraint_changes_reason ?? undefined">
            <AppButton
              label="Add constraint"
              variant="secondary"
              size="sm"
              :disable="query.data.value.constraint_changes_supported !== true"
              data-testid="structure-add-constraint"
              @click="openConstraint"
            />
            <AppTooltip v-if="query.data.value.constraint_changes_supported !== true && query.data.value.constraint_changes_reason">
              {{ query.data.value.constraint_changes_reason }}
            </AppTooltip>
          </span>
        </div>
        <AppEmptyState
          v-if="foreignKeys.length === 0 && otherConstraints.length === 0"
          text="None"
        />
        <ul
          v-else
          class="structure-view__list"
        >
          <li
            v-for="key in foreignKeys"
            :key="key.name"
            class="structure-view__index"
            data-testid="structure-fk"
            :data-constraint="key.name"
          >
            <span>
              {{ foreignKeyLabel(key) }}
              <template v-if="key.validated === false"> · not validated</template>
            </span>
            <AppIconButton
              icon="delete_outline"
              :tooltip="constraintTooltip(key.name)"
              variant="danger-quiet"
              :disable="query.data.value?.constraint_changes_supported !== true"
              :loading="droppingConstraint === key.name"
              :data-testid="`structure-drop-constraint-${key.name}`"
              @click="removeConstraint(key.name)"
            />
          </li>
          <li
            v-for="constraint in otherConstraints"
            :key="constraint.name"
            class="structure-view__index"
            :data-constraint="constraint.name"
          >
            <span>{{ constraint.kind }} · {{ constraint.name }}</span>
            <AppIconButton
              icon="delete_outline"
              :tooltip="constraintTooltip(constraint.name)"
              variant="danger-quiet"
              :disable="query.data.value?.constraint_changes_supported !== true"
              :loading="droppingConstraint === constraint.name"
              :data-testid="`structure-drop-constraint-${constraint.name}`"
              @click="removeConstraint(constraint.name)"
            />
          </li>
        </ul>
      </AppSection>

      <AppSection divided>
        <div class="structure-view__heading">
          <div class="structure-view__title">
            Indexes
          </div>
          <span :title="query.data.value.index_changes_supported ? undefined : query.data.value.index_changes_reason ?? undefined">
            <AppButton
              label="Add index"
              variant="secondary"
              size="sm"
              :disable="query.data.value.index_changes_supported !== true"
              data-testid="structure-add-index"
              @click="openIndex"
            />
            <AppTooltip v-if="query.data.value.index_changes_supported !== true && query.data.value.index_changes_reason">
              {{ query.data.value.index_changes_reason }}
            </AppTooltip>
          </span>
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
            class="structure-view__index"
            :data-testid="`structure-index-row-${index.name}`"
          >
            <span>
              {{ index.name }} · {{ index.method }}
              <template v-if="(index.columns ?? []).length">
                ({{ (index.columns ?? []).join(", ") }})
              </template>
              <template v-if="index.unique"> · unique</template>
              <template v-if="index.valid === false"> · invalid</template>
            </span>
            <AppIconButton
              icon="delete_outline"
              :tooltip="query.data.value?.index_changes_supported === true ? `Drop index ${index.name}` : query.data.value?.index_changes_reason ?? 'This index cannot be dropped'"
              variant="danger-quiet"
              :disable="query.data.value?.index_changes_supported !== true"
              :loading="droppingIndex === index.name"
              :data-testid="`structure-drop-index-${index.name}`"
              @click="removeIndex(index.name)"
            />
          </li>
        </ul>
      </AppSection>

      <DeclaredReferencesSection
        :connector-id="connectorId"
        :node-id="nodeId"
        :node-label="query.data.value.name"
      />
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
    <AddConstraintDialog
      v-if="constraintOpen"
      :model-value="true"
      :connector-id="connectorId"
      :node-id="nodeId"
      :columns="(query.data.value?.columns ?? []).map((column) => column.name)"
      :blocked="constraintBlocked"
      :saving="createConstraint.isPending.value"
      :error="constraintError"
      @save="saveConstraint"
      @update:model-value="constraintOpen = false"
    />
    <CreateIndexDialog
      v-if="indexOpen"
      :model-value="true"
      :columns="(query.data.value?.columns ?? []).map((column) => column.name)"
      :methods="query.data.value?.index_methods ?? []"
      :blocked="indexBlocked"
      :saving="createIndex.isPending.value"
      :error="indexError"
      @save="saveIndex"
      @update:model-value="indexOpen = false"
    />
    <ColumnTypeDialog
      v-if="typeColumn !== null"
      :model-value="true"
      :name="typeColumn.name"
      :current-type="typeColumn.currentType"
      :types="query.data.value?.column_type_options ?? []"
      :blocked="typeBlocked"
      :saving="columnType.isPending.value"
      :error="typeError"
      @save="changeType"
      @update:model-value="typeColumn = null"
    />
    <ColumnNullabilityDialog
      v-if="nullabilityColumn !== null"
      :model-value="true"
      :name="nullabilityColumn.name"
      :nullable="nullabilityColumn.nullable"
      :blocked="nullabilityBlocked"
      :saving="columnNullability.isPending.value"
      :error="nullabilityError"
      @save="changeNullability"
      @update:model-value="nullabilityColumn = null"
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
.structure-view__index {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.structure-view__facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 16px;
  margin: 0;
  font-size: 12px;
}
.structure-view__facts dt {
  color: var(--dp-text-muted);
}
.structure-view__facts dd {
  margin: 0;
}
</style>
