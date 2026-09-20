<script setup lang="ts">
import { ref, watch } from "vue"

import { useUnlockSshKey } from "@/features/sshKeys/api"
import { unlockOptions } from "@/features/sshKeys/keys"
import type { UnlockMinutes } from "@/features/sshKeys/keys"
import { messageOf } from "@/shared/api/errors"
import { AppButton, AppForm, AppInput, AppSelect, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * Opening a key that asks for its passphrase, for as long as is chosen (D147).
 *
 * The passphrase is checked against the key before it is held, so a mistyped
 * one is said here rather than as a failed sign-in somewhere else later.
 */
const props = defineProps<{
  /** The key to open, or null while the window is shut. */
  keyId: string | null
  /** What the key is called, for the title. */
  keyName: string
}>()
// `unlocked` before `close`, so a screen can read again what failed for want
// of the key; `close` alone is somebody changing their mind.
const emit = defineEmits<{ close: []; unlocked: [] }>()

const toast = useToast()
const unlock = useUnlockSshKey()
const passphrase = ref("")
const minutes = ref<UnlockMinutes>(15)
const error = ref("")
const spans = unlockOptions()

watch(
  () => props.keyId,
  () => {
    passphrase.value = ""
    error.value = ""
  }
)

async function open() {
  if (props.keyId === null || passphrase.value === "") return
  error.value = ""
  try {
    await unlock.mutateAsync({
      keyId: props.keyId,
      body: { passphrase: passphrase.value, minutes: minutes.value },
    })
    toast.success(`${props.keyName} is unlocked`)
    emit("unlocked")
    emit("close")
  } catch (cause) {
    error.value = messageOf(cause, "The key could not be unlocked")
  }
}
</script>

<template>
  <WindowDialog
    :model-value="keyId !== null"
    :title="`Unlock ${keyName}`"
    size="md"
    sizing="content"
    data-testid="unlock-key-dialog"
    @update:model-value="!$event && emit('close')"
  >
    <AppForm layout="section">
      <AppInput
        v-model="passphrase"
        type="password"
        label="Passphrase"
        autofocus
        autocomplete="new-password"
        :error="error"
        data-testid="unlock-key-passphrase"
        @keyup.enter="open"
      />
      <AppSelect
        :model-value="minutes"
        :options="spans"
        label="Keep it open for"
        hint="Held in memory only, and forgotten when the server restarts"
        data-testid="unlock-key-minutes"
        @update:model-value="minutes = $event as UnlockMinutes"
      />
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('close')"
      />
      <AppButton
        label="Unlock"
        :disable="passphrase === ''"
        :loading="unlock.isPending.value"
        data-testid="unlock-key-confirm"
        @click="open"
      />
    </template>
  </WindowDialog>
</template>
