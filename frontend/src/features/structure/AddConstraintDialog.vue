<script setup lang="ts">
import { computed, ref, toRef, watch } from "vue"

import type { CandidateKey } from "@/client"
import { useCandidateKeys, useSiblingTables } from "@/features/structure/api"
import type { RefAction } from "@/features/structure/model"
import {
  AppBanner,
  AppButton,
  AppForm,
  AppSelect,
  AppSpinner,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  modelValue: boolean
  connectorId: string
  nodeId: string
  columns: string[]
  /** What the source counted as standing in the way, and of which promise. */
  blocked: { kind: "repeating" | "unmatched"; count: number; exact: boolean } | null
  saving: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  save: [
    value:
      | { kind: "unique"; columns: string[] }
      | {
          kind: "foreign_key"
          columns: string[]
          targetNodeId: string
          targetColumns: string[]
          onUpdate: RefAction
          onDelete: RefAction
        },
  ]
}>()

const KINDS = [
  { label: "Unique", value: "unique" },
  { label: "Foreign key", value: "foreign_key" },
]
// The same closed set the relation model reports, so nothing new is invented.
const ACTIONS: { label: string; value: RefAction }[] = [
  { label: "No action", value: "no_action" },
  { label: "Restrict", value: "restrict" },
  { label: "Cascade", value: "cascade" },
  { label: "Set null", value: "set_null" },
  { label: "Set default", value: "set_default" },
]

const kind = ref<"unique" | "foreign_key">("unique")
const chosen = ref<string[]>([])
const targetNodeId = ref("")
const targetKeyName = ref("")
const onUpdate = ref<RefAction>("no_action")
const onDelete = ref<RefAction>("no_action")

const connectorId = toRef(props, "connectorId")
const nodeId = toRef(props, "nodeId")
const targets = useSiblingTables(connectorId, nodeId)
const target = useCandidateKeys(connectorId, targetNodeId)

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    kind.value = "unique"
    chosen.value = []
    targetNodeId.value = ""
    targetKeyName.value = ""
    onUpdate.value = "no_action"
    onDelete.value = "no_action"
  },
  { immediate: true }
)

const keys = computed<CandidateKey[]>(() => target.data.value?.candidate_keys ?? [])
const chosenKey = computed(() =>
  keys.value.find((key) => key.name === targetKeyName.value)
)
// The target says which column sets may be pointed at, so a key of the wrong
// width is never offered rather than refused after the fact.
const usableKeys = computed(() =>
  keys.value.filter((key) => key.columns.length === chosen.value.length)
)

watch([targetNodeId, usableKeys], () => {
  if (!usableKeys.value.some((key) => key.name === targetKeyName.value)) {
    targetKeyName.value = usableKeys.value[0]?.name ?? ""
  }
})

const ready = computed(() => {
  if (chosen.value.length === 0) return false
  if (kind.value === "unique") return true
  return targetNodeId.value !== "" && chosenKey.value !== undefined
})

const blockedText = computed(() => {
  if (props.blocked === null) return ""
  const many = props.blocked.count !== 1
  if (props.blocked.kind === "repeating") {
    const values = props.blocked.exact
      ? `${props.blocked.count} ${many ? "values" : "value"}`
      : `More than ${props.blocked.count} values`
    return `${values} already appear more than once, so this cannot be promised.`
  }
  const rows = props.blocked.exact
    ? `${props.blocked.count} ${many ? "rows" : "row"}`
    : `More than ${props.blocked.count} rows`
  return `${rows} point at nothing in the chosen relation. Correct or remove them first.`
})

function save() {
  if (kind.value === "unique") {
    emit("save", { kind: "unique", columns: chosen.value })
    return
  }
  const key = chosenKey.value
  if (key === undefined) return
  emit("save", {
    kind: "foreign_key",
    columns: chosen.value,
    targetNodeId: targetNodeId.value,
    targetColumns: key.columns,
    onUpdate: onUpdate.value,
    onDelete: onDelete.value,
  })
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    sizing="stable"
    title="Add constraint"
    subtitle="The source names it and says what may be pointed at"
    size="form"
    data-testid="structure-constraint-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="structure-constraint-error"
      >
        {{ error }}
      </AppBanner>
      <!-- Nothing failed: the source counted and promised nothing. -->
      <AppBanner
        v-if="blocked !== null"
        tone="warning"
        data-testid="structure-constraint-blocked"
      >
        {{ blockedText }}
      </AppBanner>
      <AppSelect
        :model-value="kind"
        :options="KINDS"
        label="Kind"
        :disable="saving"
        data-testid="structure-constraint-kind"
        @update:model-value="kind = $event as 'unique' | 'foreign_key'"
      />
      <AppSelect
        :model-value="chosen"
        :options="columns"
        label="Columns, in order"
        multiple
        :disable="saving"
        data-testid="structure-constraint-columns"
        @update:model-value="chosen = $event as string[]"
      />
      <template v-if="kind === 'foreign_key'">
        <AppSelect
          :model-value="targetNodeId"
          :options="(targets.data.value ?? []).map((node) => ({ label: node.name, value: node.id }))"
          label="Points at"
          :loading="targets.isFetching.value"
          :disable="saving"
          data-testid="structure-constraint-target"
          @update:model-value="targetNodeId = String($event)"
        />
        <AppSpinner v-if="target.isFetching.value" />
        <AppBanner
          v-else-if="targetNodeId !== '' && usableKeys.length === 0"
          tone="info"
          data-testid="structure-constraint-no-key"
        >
          That relation has no unique key of {{ chosen.length }}
          {{ chosen.length === 1 ? "column" : "columns" }} to point at.
        </AppBanner>
        <AppSelect
          v-else-if="targetNodeId !== ''"
          :model-value="targetKeyName"
          :options="usableKeys.map((key) => ({ label: `${key.name} (${key.columns.join(', ')})`, value: key.name }))"
          label="Key"
          :disable="saving"
          data-testid="structure-constraint-key"
          @update:model-value="targetKeyName = String($event)"
        />
        <AppSelect
          :model-value="onUpdate"
          :options="ACTIONS"
          label="On update"
          :disable="saving"
          data-testid="structure-constraint-on-update"
          @update:model-value="onUpdate = $event as RefAction"
        />
        <AppSelect
          :model-value="onDelete"
          :options="ACTIONS"
          label="On delete"
          :disable="saving"
          data-testid="structure-constraint-on-delete"
          @update:model-value="onDelete = $event as RefAction"
        />
      </template>
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        label="Add"
        :disable="!ready"
        :loading="saving"
        data-testid="structure-constraint-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>
