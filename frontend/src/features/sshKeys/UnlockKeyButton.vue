<script setup lang="ts">
import { ref } from "vue"

import type { SshKeyPublic } from "@/client"
import UnlockKeyDialog from "@/features/sshKeys/UnlockKeyDialog.vue"
import { AppButton } from "@/shared/ui"

/**
 * "Unlock the key", and the window that does it (D147).
 *
 * Unlocking reads again every read that failed, so a screen whose read is a
 * query needs nothing more; one whose read is not listens to `unlocked`.
 */
withDefaults(
  defineProps<{
    sshKey: SshKeyPublic
    variant?: "quiet" | "secondary"
    size?: "sm" | "md"
  }>(),
  { variant: "quiet", size: "md" }
)
const emit = defineEmits<{ unlocked: [] }>()

const unlocking = ref<SshKeyPublic | null>(null)
</script>

<template>
  <AppButton
    :variant="variant"
    :size="size"
    label="Unlock the key"
    data-testid="unlock-key"
    @click="unlocking = sshKey"
  />
  <UnlockKeyDialog
    :key-id="unlocking?.id ?? null"
    :key-name="unlocking?.name ?? ''"
    @unlocked="emit('unlocked')"
    @close="unlocking = null"
  />
</template>
