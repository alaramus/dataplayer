<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import type { DeclaredReferencePublic } from "@/client"
import { useDeclaredReferences, useUndeclareReference } from "@/features/declared/api"
import { farLabel, sidesFrom } from "@/features/declared/model"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppBanner,
  AppButton,
  AppEmptyState,
  AppIconButton,
  AppSection,
  AppSpinner,
  useConfirm,
  useToast,
} from "@/shared/ui"

import DeclareReferenceDialog from "./DeclareReferenceDialog.vue"

/**
 * The references somebody drew from this node, and the way to draw another.
 *
 * Beside the constraints and the indexes because that is what it is: a key
 * this node has, kept by the application instead of by the source (D106). The
 * difference is said by the section it is in rather than by a badge that would
 * have to be explained.
 */
const props = defineProps<{
  connectorId: string
  nodeId: string
  nodeLabel: string
}>()

const query = useDeclaredReferences(
  () => props.connectorId,
  () => props.nodeId
)
const undeclare = useUndeclareReference()
const confirm = useConfirm()
const toast = useToast()
const open = ref(false)
const removing = ref<string | null>(null)

interface Drawn {
  id: string
  from: string
  to: string
  connectorIds: string[]
}

const drawn = computed<Drawn[]>(() =>
  (query.data.value ?? []).flatMap((reference: DeclaredReferencePublic) => {
    const sides = sidesFrom(reference, props.connectorId, props.nodeId)
    if (sides === null) return []
    return [
      {
        id: reference.id,
        from: sides.near.column,
        to: farLabel(sides.far, props.connectorId),
        connectorIds: reference.ends.map((end) => end.connector_id),
      },
    ]
  })
)

/**
 * Asked before removing, like every other thing on this panel that goes.
 *
 * The question says what is lost and what is not: a declared reference is a
 * record of this application's, so removing one takes away the way out and
 * changes neither source (D106).
 */
async function remove(reference: Drawn) {
  const accepted = await confirm({
    title: t("declared.remove.title"),
    message: t("declared.remove.message", { from: reference.from, to: reference.to }),
    confirmLabel: t("declared.remove.confirm"),
    danger: true,
  })
  if (!accepted) return
  removing.value = reference.id
  try {
    await undeclare.mutateAsync({
      referenceId: reference.id,
      connectorIds: reference.connectorIds,
    })
    toast.success(t("declared.remove.done"))
  } catch (error) {
    toast.error(messageOf(error, t("declared.remove.failed")))
  } finally {
    removing.value = null
  }
}
</script>

<template>
  <AppSection divided>
    <div class="declared__heading">
      <div class="declared__title">
        {{ t("declared.title") }}
      </div>
      <AppButton
        :label="t('declared.declare_one')"
        variant="secondary"
        size="sm"
        data-testid="structure-declare-reference"
        @click="open = true"
      />
    </div>
    <!-- A list that could not be read says so; what a removal did is said by
         a toast, the way the sections above this one say it. -->
    <AppBanner
      v-if="query.isError.value"
      tone="error"
      data-testid="declared-error"
    >
      {{ messageOf(query.error.value, t("declared.read_failed")) }}
    </AppBanner>
    <AppSpinner v-if="query.isPending.value" />
    <AppEmptyState
      v-else-if="drawn.length === 0"
      :text="t('declared.none')"
    />
    <ul
      v-else
      class="declared__list"
    >
      <li
        v-for="reference in drawn"
        :key="reference.id"
        class="declared__item"
        data-testid="declared-reference"
        :data-reference="reference.id"
      >
        <span>{{ reference.from }} → {{ reference.to }}</span>
        <AppIconButton
          :icon="appIcons.deleteOutline"
          :tooltip="t('declared.remove_tooltip')"
          variant="danger-quiet"
          :loading="removing === reference.id"
          :data-testid="`declared-remove-${reference.id}`"
          @click="remove(reference)"
        />
      </li>
    </ul>

    <DeclareReferenceDialog
      v-if="open"
      v-model="open"
      :connector-id="connectorId"
      :node-id="nodeId"
      :node-label="nodeLabel"
    />
  </AppSection>
</template>

<style scoped>
.declared__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-2);
}
.declared__title {
  font-weight: 600;
}
.declared__list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.declared__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-2);
  padding: var(--dp-space-half) 0;
}
</style>
