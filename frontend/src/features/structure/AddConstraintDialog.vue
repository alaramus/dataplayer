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
import { t } from "@/shared/i18n"
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

const KINDS = computed(() => [
  { label: t("structure.add_constraint.kinds.unique"), value: "unique" },
  { label: t("structure.add_constraint.kinds.foreign_key"), value: "foreign_key" },
])
// The same closed set the relation model reports, so nothing new is invented.
const REF_ACTIONS: RefAction[] = ["no_action", "restrict", "cascade", "set_null", "set_default"]
const ACTIONS = computed(() =>
  REF_ACTIONS.map((value) => ({ label: t(`structure.add_constraint.actions.${value}`), value }))
)

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
  const n = props.blocked.count
  if (props.blocked.kind === "repeating") {
    return t(
      props.blocked.exact
        ? "structure.add_constraint.repeating"
        : "structure.add_constraint.repeating_more",
      { n },
      n
    )
  }
  return t(
    props.blocked.exact
      ? "structure.add_constraint.unmatched"
      : "structure.add_constraint.unmatched_more",
    { n },
    n
  )
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
    :title="t('structure.add_constraint.title')"
    :subtitle="t('structure.add_constraint.subtitle')"
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
        :label="t('structure.add_constraint.kind')"
        :disable="saving"
        data-testid="structure-constraint-kind"
        @update:model-value="kind = $event as 'unique' | 'foreign_key'"
      />
      <AppSelect
        :model-value="chosen"
        :options="columns"
        :label="t('structure.add_constraint.columns')"
        multiple
        :disable="saving"
        data-testid="structure-constraint-columns"
        @update:model-value="chosen = $event as string[]"
      />
      <template v-if="kind === 'foreign_key'">
        <AppSelect
          :model-value="targetNodeId"
          :options="(targets.data.value ?? []).map((node) => ({ label: node.name, value: node.id }))"
          :label="t('structure.add_constraint.points_at')"
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
          {{ t('structure.add_constraint.no_key', { n: chosen.length }, chosen.length) }}
        </AppBanner>
        <AppSelect
          v-else-if="targetNodeId !== ''"
          :model-value="targetKeyName"
          :options="usableKeys.map((key) => ({ label: `${key.name} (${key.columns.join(', ')})`, value: key.name }))"
          :label="t('structure.add_constraint.key')"
          :disable="saving"
          data-testid="structure-constraint-key"
          @update:model-value="targetKeyName = String($event)"
        />
        <AppSelect
          :model-value="onUpdate"
          :options="ACTIONS"
          :label="t('structure.add_constraint.on_update')"
          :disable="saving"
          data-testid="structure-constraint-on-update"
          @update:model-value="onUpdate = $event as RefAction"
        />
        <AppSelect
          :model-value="onDelete"
          :options="ACTIONS"
          :label="t('structure.add_constraint.on_delete')"
          :disable="saving"
          data-testid="structure-constraint-on-delete"
          @update:model-value="onDelete = $event as RefAction"
        />
      </template>
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="t('structure.add_constraint.add')"
        :disable="!ready"
        :loading="saving"
        data-testid="structure-constraint-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>
