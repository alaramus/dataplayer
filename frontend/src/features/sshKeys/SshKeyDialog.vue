<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { useGenerateSshKey, useImportSshKey } from "@/features/sshKeys/api"
import { codeParts, codePlaces, readKeyFile } from "@/features/sshKeys/keys"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppButton,
  AppFileInput,
  AppForm,
  AppInput,
  AppSelect,
  useToast,
} from "@/shared/ui"
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
const emit = defineEmits<{
  "update:modelValue": [open: boolean]
  /** The id of the key just made or imported, so a form can point at it. */
  created: [id: string]
}>()

const toast = useToast()
const generate = useGenerateSshKey()
const keep = useImportSshKey()

const name = ref("")
const keyType = ref<"ed25519" | "rsa">("ed25519")
const privateKey = ref("")
/** A key file chosen or dropped, whose text becomes the key above. */
const keyFile = ref<File | null>(null)
const passphrase = ref("")
const remember = ref<"ask" | "stored">("ask")
const error = ref("")

const keyTypes = computed(() => [
  { label: "ED25519", value: "ed25519", description: t("ssh_keys.dialog.ed25519_hint") },
  { label: "RSA 4096", value: "rsa", description: t("ssh_keys.dialog.rsa_hint") },
])
const rememberOptions = computed(() => [
  { label: t("ssh_keys.dialog.ask"), value: "ask", description: t("ssh_keys.dialog.ask_hint") },
  { label: t("ssh_keys.dialog.keep"), value: "stored", description: t("ssh_keys.dialog.keep_hint") },
])

const WHERE_CODES = { ed25519: "id_ed25519", rsa: "id_rsa", folder: ".ssh", pub: ".pub" }
const whereParts = computed(() =>
  codeParts(t("ssh_keys.dialog.where", codePlaces(WHERE_CODES)), WHERE_CODES)
)

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
    keyFile.value = null
    passphrase.value = ""
    error.value = ""
  }
)

// The file's text fills the field, where it can be looked at before anything
// is sent; the name follows the file's when nothing was typed there yet.
watch(keyFile, async (file) => {
  if (file === null) return
  error.value = ""
  try {
    privateKey.value = await readKeyFile(file)
    if (name.value.trim() === "") name.value = file.name
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t("ssh_keys.dialog.file_unreadable")
  }
})

async function save() {
  if (!ready.value || busy.value) return
  error.value = ""
  const protection = {
    passphrase: passphrase.value === "" ? null : passphrase.value,
    passphrase_mode: remember.value,
  }
  try {
    if (props.mode === "generate") {
      const made = (await generate.mutateAsync({ name: name.value.trim(), key_type: keyType.value, ...protection }))
      toast.success(t("ssh_keys.dialog.made"))
      emit("created", made.id)
    } else {
      const kept = (await keep.mutateAsync({ name: name.value.trim(), private_key: privateKey.value, ...protection }))
      toast.success(t("ssh_keys.dialog.kept"))
      emit("created", kept.id)
    }
    emit("update:modelValue", false)
  } catch (cause) {
    error.value = messageOf(cause, t("ssh_keys.dialog.save_failed"))
  }
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="mode === 'generate' ? t('ssh_keys.dialog.title_new') : t('ssh_keys.dialog.title_import')"
    size="form"
    sizing="stable"
    data-testid="ssh-key-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppInput
        v-model="name"
        :label="t('ssh_keys.dialog.name')"
        autofocus
        data-testid="ssh-key-name"
      />
      <AppSelect
        v-if="mode === 'generate'"
        :model-value="keyType"
        :options="keyTypes"
        :label="t('ssh_keys.dialog.type')"
        data-testid="ssh-key-type"
        @update:model-value="keyType = $event as 'ed25519' | 'rsa'"
      />
      <template v-else>
        <AppFileInput
          v-model="keyFile"
          :label="t('ssh_keys.dialog.key_file')"
          data-testid="ssh-key-file"
        />
        <p class="ssh-key-dialog__where">
          <template
            v-for="(part, index) in whereParts"
            :key="index"
          >
            <code v-if="part.code">{{ part.text }}</code>
            <span v-else>{{ part.text }}</span>
          </template>
        </p>
        <AppInput
          v-model="privateKey"
          type="textarea"
          :label="t('ssh_keys.dialog.private_key')"
          autocomplete="off"
          :hint="t('ssh_keys.dialog.private_key_hint')"
          :error="error"
          data-testid="ssh-key-private"
        />
      </template>
      <AppInput
        v-model="passphrase"
        type="password"
        :label="t('ssh_keys.dialog.passphrase')"
        autocomplete="new-password"
        :hint="
          mode === 'import'
            ? t('ssh_keys.dialog.passphrase_import_hint')
            : t('ssh_keys.dialog.passphrase_generate_hint')
        "
        :error="mode === 'generate' ? error : ''"
        data-testid="ssh-key-passphrase"
      />
      <AppSelect
        v-if="passphrase !== ''"
        :model-value="remember"
        :options="rememberOptions"
        :label="t('ssh_keys.dialog.remember')"
        data-testid="ssh-key-remember"
        @update:model-value="remember = $event as 'ask' | 'stored'"
      />
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="mode === 'generate' ? t('ssh_keys.dialog.make') : t('ssh_keys.dialog.import')"
        :disable="!ready"
        :loading="busy"
        data-testid="ssh-key-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.ssh-key-dialog__where {
  margin: 0;
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
}
</style>
