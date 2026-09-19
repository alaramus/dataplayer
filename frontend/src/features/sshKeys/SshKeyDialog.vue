<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { useGenerateSshKey, useImportSshKey } from "@/features/sshKeys/api"
import { messageOf } from "@/shared/api/errors"
import { AppButton, AppInput, AppSection, AppSelect, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * Making a key here, or keeping one somebody already has (D146).
 *
 * One window for both, because the two ask the same questions but one: a
 * made key needs a type, a kept one needs its text. The passphrase is what
 * the key will be locked with from now on — for a key that arrives encrypted,
 * the one that opens it.
 */
const props = defineProps<{ modelValue: boolean; mode: "generate" | "import" }>()
const emit = defineEmits<{ "update:modelValue": [open: boolean] }>()

const toast = useToast()
const generate = useGenerateSshKey()
const keep = useImportSshKey()

const name = ref("")
const keyType = ref<"ed25519" | "rsa">("ed25519")
const privateKey = ref("")
const passphrase = ref("")
const remember = ref<"ask" | "stored">("ask")
const error = ref("")

const keyTypes = [
  { label: "ED25519", value: "ed25519", description: "What every current server accepts" },
  { label: "RSA 4096", value: "rsa", description: "For old servers that refuse ED25519" },
]
const rememberOptions = [
  {
    label: "Ask for it",
    value: "ask",
    description: "Held in memory for a while after you type it; a copy of the server opens nothing",
  },
  { label: "Keep it", value: "stored", description: "Kept encrypted beside the key; never asked for" },
]

const busy = computed(() => generate.isPending.value || keep.isPending.value)
const ready = computed(
  () => name.value.trim() !== "" && (props.mode === "generate" || privateKey.value.trim() !== "")
)

// A window opened again starts empty: a pasted private key must not wait in a
// closed one for the next person at this screen.
watch(
  () => props.modelValue,
  (open) => {
    if (open) return
    name.value = ""
    privateKey.value = ""
    passphrase.value = ""
    error.value = ""
  }
)

async function save() {
  if (!ready.value || busy.value) return
  error.value = ""
  const protection = {
    passphrase: passphrase.value === "" ? null : passphrase.value,
    passphrase_mode: remember.value,
  }
  try {
    if (props.mode === "generate") {
      await generate.mutateAsync({ name: name.value.trim(), key_type: keyType.value, ...protection })
      toast.success("Key made. Add its public key to the servers it should open")
    } else {
      await keep.mutateAsync({ name: name.value.trim(), private_key: privateKey.value, ...protection })
      toast.success("Key kept")
    }
    emit("update:modelValue", false)
  } catch (cause) {
    error.value = messageOf(cause, "The key could not be saved")
  }
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="mode === 'generate' ? 'New SSH key' : 'Import an SSH key'"
    size="md"
    data-testid="ssh-key-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppInput
        v-model="name"
        label="Name"
        autofocus
        data-testid="ssh-key-name"
      />
      <AppSelect
        v-if="mode === 'generate'"
        :model-value="keyType"
        :options="keyTypes"
        label="Type"
        data-testid="ssh-key-type"
        @update:model-value="keyType = $event as 'ed25519' | 'rsa'"
      />
      <AppInput
        v-else
        v-model="privateKey"
        type="textarea"
        label="Private key"
        autocomplete="off"
        hint="The text of the key file, OpenSSH or PEM. It is never shown again."
        :error="error"
        data-testid="ssh-key-private"
      />
      <AppInput
        v-model="passphrase"
        type="password"
        label="Passphrase"
        autocomplete="new-password"
        :hint="
          mode === 'import'
            ? 'The one that opens the key, or a new one to lock a key that has none'
            : 'Optional. Without one the key opens for anybody who holds this server'
        "
        :error="mode === 'generate' ? error : ''"
        data-testid="ssh-key-passphrase"
      />
      <AppSelect
        v-if="passphrase !== ''"
        :model-value="remember"
        :options="rememberOptions"
        label="The passphrase"
        data-testid="ssh-key-remember"
        @update:model-value="remember = $event as 'ask' | 'stored'"
      />
    </AppSection>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="mode === 'generate' ? 'Make key' : 'Import'"
        :disable="!ready"
        :loading="busy"
        data-testid="ssh-key-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>
