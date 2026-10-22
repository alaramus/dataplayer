<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref, toRef } from "vue"

import { useAdapterTypes, useConnectors } from "@/features/connectors/api"
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
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import { badgesFor, datasetFacts, foreignKeyLabel } from "@/features/structure/model"
import type { ForeignKey, RefAction } from "@/features/structure/model"
import { errorKindOf, messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppBadge,
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
const connectors = useConnectors()
const adapterTypes = useAdapterTypes()
const supportsDeclaredReferences = computed(() => {
  const connector = connectors.data.value?.data.find(
    (one) => one.id === props.connectorId
  )
  const source = adapterTypes.data.value?.find(
    (one) => one.name === connector?.adapter_type
  )
  return source?.capabilities.some((one) => one.code === "declared_references") === true
})
const refreshModel = ref(false)
const query = useRelationModel(connectorId, nodeId, undefined, refreshModel)
const errorKind = computed(() => errorKindOf(query.error.value))
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

async function reload() {
  refreshModel.value = true
  try { await query.refetch() }
  finally { refreshModel.value = false }
}
defineExpose({ reload })

const COLUMNS = computed(() => [
  { name: "name", label: t("structure.view.table.column"), field: "name", align: "left" as const },
  { name: "type", label: t("structure.view.table.type"), field: "type", align: "left" as const },
  { name: "nullable", label: t("structure.view.table.nullable"), field: "nullable", align: "left" as const },
  // A default can be a whole expression; it is cut in its own column rather
  // than pushing the commands of every row past the panel's edge.
  {
    name: "default", label: t("structure.view.table.default"), field: "default", align: "left" as const,
    classes: "structure-view__default", headerClasses: "structure-view__default",
  },
  { name: "keys", label: t("structure.view.table.keys"), field: "keys", align: "left" as const },
  // Held at the right edge while the columns scroll under it: at 1440 the
  // table was wider than its panel and Drop stood outside it (D187).
  {
    name: "actions", label: "", field: "actions", align: "right" as const,
    classes: "structure-view__actions", headerClasses: "structure-view__actions",
  },
])

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
    : messageOf(query.error.value, t("structure.view.read_failed"))
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
    toast.success(t("structure.view.column_added", { name: value.name }))
  } catch (error) {
    addError.value = messageOf(error, t("structure.view.add_column_failed"))
  }
}

async function drop(name: string) {
  const accepted = await confirm({
    title: t("structure.view.drop_column_title", { name }),
    message: t("structure.view.drop_column_message"),
    confirmLabel: t("structure.view.drop"),
    danger: true,
  })
  if (!accepted) return
  dropping.value = name
  try {
    await dropColumn.mutateAsync({ node_id: props.nodeId, name })
    toast.success(t("structure.view.column_dropped", { name }))
  } catch (error) {
    toast.error(messageOf(error, t("structure.view.drop_column_failed")))
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
    toast.success(t("structure.view.column_renamed", { name, new_name: newName }))
  } catch (error) {
    renameError.value = messageOf(error, t("structure.view.rename_column_failed"))
  }
}

function openDefault(name: string, currentDefault: string | null) {
  defaultError.value = ""
  defaultColumn.value = { name, currentDefault }
}

function constraintTooltip(name: string): string {
  const model = query.data.value
  if (model?.constraint_changes_supported !== true) {
    return model?.constraint_changes_reason ?? t("structure.view.constraint_fixed")
  }
  return t("structure.view.drop_constraint", { name })
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
    return model?.column_changes_reason ?? t("structure.view.column_fixed")
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
    toast.success(t("structure.view.type_changed", { name: column.name, type: result.type_sql }))
  } catch (error) {
    typeError.value = messageOf(error, t("structure.view.change_type_failed"))
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
    toast.success(t("structure.view.constraint_added", { name: result.name }))
  } catch (error) {
    constraintError.value = messageOf(error, t("structure.view.add_constraint_failed"))
  }
}

async function removeConstraint(name: string) {
  const accepted = await confirm({
    title: t("structure.view.drop_constraint_title", { name }),
    message: t("structure.view.drop_constraint_message"),
    confirmLabel: t("structure.view.drop"),
    danger: true,
  })
  if (!accepted) return
  droppingConstraint.value = name
  try {
    await dropConstraint.mutateAsync({ node_id: props.nodeId, name })
    toast.success(t("structure.view.constraint_dropped", { name }))
  } catch (error) {
    toast.error(messageOf(error, t("structure.view.drop_constraint_failed")))
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
    toast.success(t("structure.view.index_created", { name: result.name }))
  } catch (error) {
    indexError.value = messageOf(error, t("structure.view.create_index_failed"))
  }
}

async function removeIndex(name: string) {
  const accepted = await confirm({
    title: t("structure.view.drop_index_title", { name }),
    message: t("structure.view.drop_index_message"),
    confirmLabel: t("structure.view.drop"),
    danger: true,
  })
  if (!accepted) return
  droppingIndex.value = name
  try {
    await dropIndex.mutateAsync({ node_id: props.nodeId, name })
    toast.success(t("structure.view.index_dropped", { name }))
  } catch (error) {
    toast.error(messageOf(error, t("structure.view.drop_index_failed")))
  } finally {
    droppingIndex.value = null
  }
}

function nullabilityTooltip(nullable: boolean): string {
  return changeTooltip(
    "nullability",
    nullable ? t("structure.view.require_every_row") : t("structure.view.allow_no_value")
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
        ? t("structure.view.now_nullable", { name: column.name })
        : t("structure.view.now_required", { name: column.name })
    )
  } catch (error) {
    nullabilityError.value = messageOf(error, t("structure.view.change_column_failed"))
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
    toast.success(
      action === "set"
        ? t("structure.view.default_set", { name: column.name })
        : t("structure.view.default_dropped", { name: column.name })
    )
  } catch (error) {
    defaultError.value = messageOf(error, t("structure.view.change_default_failed"))
  }
}
</script>

<template>
  <div
    class="structure-view"
    data-testid="structure-view"
  >
    <SourceErrorBanner
      v-if="errorText"
      :connector-id="connectorId"
      :error-kind="errorKind"
      data-testid="structure-error"
    >
      {{ errorText }}
    </SourceErrorBanner>

    <AppSpinner v-else-if="query.isPending.value" />

    <template v-else-if="query.data.value">
      <AppSection
        v-if="facts.length > 0"
        data-testid="structure-format"
      >
        <div class="structure-view__title">
          {{ t('structure.view.format') }}
        </div>
        <dl class="structure-view__facts">
          <template
            v-for="fact in facts"
            :key="fact.key"
          >
            <dt>{{ fact.label }}</dt>
            <dd :data-testid="`structure-fact-${fact.key}`">
              {{ fact.value }}
            </dd>
          </template>
        </dl>
      </AppSection>

      <AppSection :divided="facts.length > 0">
        <div class="structure-view__heading">
          <div class="structure-view__title">
            {{ t('structure.view.columns') }}
          </div>
          <!-- The span is what the tooltip hangs on: a disabled button
               takes no pointer events, so a tooltip inside it would never be
               shown. It carries no `title` of its own — the two together drew
               the same sentence twice, once styled and once by the browser. -->
          <span>
            <AppButton
              :label="t('structure.view.add_column')"
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
          :empty-text="t('structure.view.no_columns')"
        >
          <!-- The fact being changed is already printed here, so it is the
               control: another icon in the row of actions would have to name
               in a tooltip which of a column's facts it changes. -->
          <template #body-cell-type="cellProps">
            <q-td :props="cellProps">
              <span
                v-if="!supportsColumn('type') || cellProps.row.generated"
                :data-testid="`structure-type-${cellProps.row.name}`"
              >
                {{ cellProps.row.type }}
                <AppTooltip>
                  {{ cellProps.row.generated
                    ? t('structure.view.generated_type')
                    : changeTooltip('type', t('structure.view.change_type', { name: cellProps.row.name })) }}
                </AppTooltip>
              </span>
              <AppButton
                v-else
                :label="String(cellProps.row.type)"
                variant="quiet"
                size="sm"
                layout="inline"
                :data-testid="`structure-type-${cellProps.row.name}`"
                @click="openType(String(cellProps.row.name), String(cellProps.row.type))"
              >
                <AppTooltip>
                  {{ cellProps.row.generated
                    ? t('structure.view.generated_type')
                    : changeTooltip('type', t('structure.view.change_type', { name: cellProps.row.name })) }}
                </AppTooltip>
              </AppButton>
            </q-td>
          </template>
          <template #body-cell-nullable="cellProps">
            <q-td :props="cellProps">
              <span
                v-if="!supportsColumn('nullability')"
                :data-testid="`structure-nullability-${cellProps.row.name}`"
              >
                {{ cellProps.row.nullable ? t('structure.view.yes') : t('structure.view.no') }}
                <AppTooltip>{{ nullabilityTooltip(cellProps.row.nullable) }}</AppTooltip>
              </span>
              <AppButton
                v-else
                :label="cellProps.row.nullable ? t('structure.view.yes') : t('structure.view.no')"
                variant="quiet"
                size="sm"
                layout="inline"
                :data-testid="`structure-nullability-${cellProps.row.name}`"
                @click="openNullability(String(cellProps.row.name), cellProps.row.nullable)"
              >
                <AppTooltip>{{ nullabilityTooltip(cellProps.row.nullable) }}</AppTooltip>
              </AppButton>
            </q-td>
          </template>
          <template #body-cell-default="cellProps">
            <q-td :props="cellProps">
              <span :title="cellProps.value || undefined">{{ cellProps.value }}</span>
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
                :icon="appIcons.dataObject"
                :tooltip="cellProps.row.generated
                  ? t('structure.view.generated_default')
                  : t('structure.view.change_default', { name: cellProps.row.name })"
                :disable="!supportsColumn('default') || cellProps.row.generated"
                :data-testid="`structure-default-${cellProps.row.name}`"
                compact
                @click="openDefault(String(cellProps.row.name), cellProps.row.currentDefault)"
              />
              <AppIconButton
                :icon="appIcons.edit"
                :tooltip="changeTooltip('rename', t('structure.view.rename_column', { name: cellProps.row.name }))"
                :disable="!supportsColumn('rename')"
                :data-testid="`structure-rename-${cellProps.row.name}`"
                compact
                @click="openRename(String(cellProps.row.name))"
              />
              <AppIconButton
                :icon="appIcons.deleteOutline"
                :tooltip="changeTooltip('drop', t('structure.view.drop_column', { name: cellProps.row.name }))"
                variant="danger-quiet"
                :disable="!supportsColumn('drop')"
                :loading="dropping === cellProps.row.name"
                :data-testid="`structure-drop-${cellProps.row.name}`"
                compact
                @click="drop(String(cellProps.row.name))"
              />
            </q-td>
          </template>
        </AppTable>
      </AppSection>

      <AppSection divided>
        <div class="structure-view__heading">
          <div class="structure-view__title">
            {{ t('structure.view.constraints') }}
          </div>
          <span>
            <AppButton
              :label="t('structure.view.add_constraint')"
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
          :text="t('structure.view.none')"
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
              <template v-if="key.validated === false"> · {{ t('structure.view.not_validated') }}</template>
            </span>
            <AppIconButton
              :icon="appIcons.deleteOutline"
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
            <span>{{ t(`structure.view.constraint_kind.${constraint.kind}`) }} · {{ constraint.name }}</span>
            <AppIconButton
              :icon="appIcons.deleteOutline"
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
            {{ t('structure.view.indexes') }}
          </div>
          <span>
            <AppButton
              :label="t('structure.view.add_index')"
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
          :text="t('structure.view.none')"
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
              <template v-if="index.unique"> · {{ t('structure.view.unique') }}</template>
              <template v-if="index.valid === false"> · {{ t('structure.view.invalid') }}</template>
            </span>
            <AppIconButton
              :icon="appIcons.deleteOutline"
              :tooltip="query.data.value?.index_changes_supported === true ? t('structure.view.drop_index', { name: index.name }) : query.data.value?.index_changes_reason ?? t('structure.view.index_fixed')"
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
        v-if="supportsDeclaredReferences"
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
  margin-bottom: var(--dp-space-2);
  font-weight: 600;
}
.structure-view__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-3);
  margin-bottom: var(--dp-space-2);
}
.structure-view__heading .structure-view__title {
  margin-bottom: 0;
}
/* Inset on the right by the columns table's cell padding, so the delete of a
   constraint or an index stands under the delete of a column, 11px out
   of line before. */
.structure-view__list {
  margin: 0;
  padding: 0 var(--dp-space-4);
}
/* The table fills the panel rather than standing on it as a card, so the
   column held at the edge has a ground to hide the scrolled cells under. */
.structure-view :deep(.app-table) {
  background: var(--dp-surface);
}
.structure-view :deep(.structure-view__default) {
  max-width: var(--dp-width-name);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.structure-view :deep(.structure-view__actions) {
  position: sticky;
  right: 0;
  z-index: var(--dp-layer-sticky);
  background: var(--dp-surface);
  box-shadow: -1px 0 0 var(--dp-border-faint);
  white-space: nowrap;
}
.structure-view__index {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-2);
}
.structure-view__facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--dp-space-1) var(--dp-space-4);
  margin: 0;
  font-size: var(--dp-font-size-sm);
}
.structure-view__facts dt {
  color: var(--dp-text-muted);
}
.structure-view__facts dd {
  margin: 0;
}
</style>
