<script setup lang="ts">
import { useLockedKey } from "@/features/sshKeys/api"
import UnlockKeyButton from "@/features/sshKeys/UnlockKeyButton.vue"
import { AppBanner } from "@/shared/ui"

/**
 * A read of a source that failed, in the source's words — with the way on
 * when the way on is opening the key it signs in with (D147). Every screen
 * that shows such a failure shows it through this, so none of them reports a
 * locked key as a dead end.
 */
const props = defineProps<{
  connectorId: string
  /** The kind the failure carried, `locked` among them. */
  errorKind: string | null | undefined
}>()
const emit = defineEmits<{ unlocked: [] }>()

const lockedKey = useLockedKey(
  () => props.connectorId,
  () => props.errorKind
)
</script>

<template>
  <AppBanner tone="error">
    <slot />
    <template
      v-if="lockedKey"
      #action
    >
      <UnlockKeyButton
        :ssh-key="lockedKey"
        @unlocked="emit('unlocked')"
      />
    </template>
  </AppBanner>
</template>
