<script setup lang="ts">
import { computed, ref } from "vue"

import type { DeclaredReferencePublic } from "@/client"
import { useDeclaredReferences, useUndeclareReference } from "@/features/declared/api"
import { farLabel, sidesFrom } from "@/features/declared/model"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppEmptyState,
  AppIconButton,
  AppSection,
  AppSpinner,
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
const open = ref(false)
const removing = ref<string | null>(null)
const trouble = ref("")

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

async function remove(reference: Drawn) {
  removing.value = reference.id
  trouble.value = ""
  try {
    await undeclare.mutateAsync({
      referenceId: reference.id,
      connectorIds: reference.connectorIds,
    })
  } catch (error) {
    trouble.value = messageOf(error, "Could not remove this reference")
  } finally {
    removing.value = null
  }
}
</script>

<template>
  <AppSection divided>
    <div class="declared__heading">
      <div class="declared__title">
        Declared references
      </div>
      <AppButton
        label="Declare a reference"
        variant="secondary"
        size="sm"
        data-testid="structure-declare-reference"
        @click="open = true"
      />
    </div>
    <AppBanner
      v-if="trouble"
      tone="error"
      data-testid="declared-error"
    >
      {{ trouble }}
    </AppBanner>
    <AppSpinner v-if="query.isPending.value" />
    <AppEmptyState
      v-else-if="drawn.length === 0"
      text="None"
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
          icon="delete_outline"
          tooltip="Remove this reference"
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
  gap: 8px;
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
  gap: 8px;
  padding: 2px 0;
}
</style>
