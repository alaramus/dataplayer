<script setup lang="ts">
import { useLockedKey } from "@/features/sshKeys/api"
import UnlockKeyButton from "@/features/sshKeys/UnlockKeyButton.vue"
import { AppButton } from "@/shared/ui"

import type { Said } from "./outcomes"

/**
 * What one place says about itself in an answer, and what can be done about
 * it (D201): "Didn't answer in 2 s · Try again".
 *
 * A locked key is opened where it is said, through the same button every
 * other failed read offers (D147), and the place is asked again once it is.
 */
const props = defineProps<{
  said: Said
  /** The connection the place is, for the key it signs in with. */
  connectorId: string | null
  /** Whether to offer keeping this connection's names, a slow one's way on (D212). */
  offerKeep?: boolean
}>()

const emit = defineEmits<{
  /** The gesture was taken: ask again, or go where it says. */
  gesture: []
  /** Keep names was asked for. */
  keep: []
}>()

const lockedKey = useLockedKey(
  () => props.connectorId ?? "",
  () => (props.said.gesture?.kind === "unlock" ? "locked" : null)
)
</script>

<template>
  <div
    class="search-outcome"
    data-testid="search-outcome"
  >
    <span class="search-outcome__sentence">{{ said.sentence }}</span>
    <UnlockKeyButton
      v-if="said.gesture?.kind === 'unlock' && lockedKey"
      :ssh-key="lockedKey"
      variant="quiet"
      size="sm"
      @unlocked="emit('gesture')"
    />
    <AppButton
      v-else-if="said.gesture && said.gesture.kind !== 'unlock'"
      variant="quiet"
      size="sm"
      :label="said.gesture.label"
      data-testid="search-gesture"
      @click="emit('gesture')"
    />
    <AppButton
      v-if="offerKeep"
      variant="quiet"
      size="sm"
      label="Keep names"
      data-testid="search-keep-names"
      @click="emit('keep')"
    />
  </div>
</template>

<style scoped>
.search-outcome {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
  min-height: var(--dp-row-height-dense);
  padding: 0 var(--dp-space-3);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
}
</style>
