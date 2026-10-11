<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref, watch } from "vue"

import type { ProviderKeyState } from "@/client"
import { AppButton, AppForm, AppIconButton, AppInput, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"
import { messageOf } from "@/shared/api/errors"

import { checkAiKey, useAiSettings, useRemoveAiKey, useWriteAiKey } from "./api"
import { JEV_PROVIDER } from "./modelOptions"

type Provider = ProviderKeyState["provider"]
const props = defineProps<{
  modelValue: boolean
  provider: Provider
  providerLabel: string
  keySet: boolean
}>()
const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()
const draft = ref("")
const revealed = ref(false)
const checking = ref(false)
const writeKey = useWriteAiKey()
const removeKey = useRemoveAiKey()
const toast = useToast()
const settings = useAiSettings()
const keyPage = computed(() => settings.data.value?.keys.find((one) => one.provider === props.provider)?.key_page)
const keyPageHost = computed(() => (keyPage.value ? new URL(keyPage.value).host : ""))

watch(() => props.modelValue, (open) => { if (open) { draft.value = ""; revealed.value = false } })

async function save() {
  const key = draft.value.trim()
  if (!key) return
  try {
    await writeKey.mutateAsync({ provider: props.provider, key })
    draft.value = ""
    toast.success(props.provider === JEV_PROVIDER ? "Jev key saved" : `${props.providerLabel} key saved for all its models`)
  } catch (cause) { toast.error(messageOf(cause, "The key could not be saved")) }
}
async function check() {
  checking.value = true
  try {
    // A key is checked as typed. Saving first and checking afterwards left a
    // wrong key stored for every model of the provider until it was cleared.
    const result = await checkAiKey(props.provider, draft.value.trim() || null)
    if (result.ok) toast.success(result.message)
    else toast.error(result.message)
  } catch (cause) { toast.error(messageOf(cause, "The key could not be checked")) }
  finally { checking.value = false }
}
async function clear() {
  try { await removeKey.mutateAsync(props.provider); draft.value = ""; toast.info(`${props.providerLabel} key removed`) }
  catch (cause) { toast.error(messageOf(cause, "The key could not be removed")) }
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="`${providerLabel} API key`"
    :subtitle="provider === JEV_PROVIDER ? 'Required for the Jev change mode. The key is verified before it is saved.' : `This key is shared by every ${providerLabel} model. Check works before saving.`"
    size="md"
    sizing="content"
    data-testid="ai-key-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppInput
        v-model="draft"
        :type="revealed ? 'text' : 'password'"
        label="API key"
        :placeholder="keySet ? 'A key is already set' : undefined"
        autocomplete="new-password"
        data-testid="ai-provider-key"
        @keyup.enter="save"
      >
        <template #after>
          <AppIconButton
            :icon="revealed ? appIcons.visibilityOff : appIcons.visibility"
            :tooltip="revealed ? 'Hide key' : 'Show key'"
            @click="revealed = !revealed"
          />
        </template>
      </AppInput>
      <p
        v-if="keyPage"
        class="ai-key-dialog__page"
      >
        {{ keySet ? "Keys are issued at" : "No key yet? Create one at" }}
        <a
          :href="keyPage"
          target="_blank"
          rel="noopener noreferrer"
          data-testid="ai-key-page"
        >
          {{ keyPageHost }}<q-icon
            :name="appIcons.openInNew"
            class="ai-key-dialog__page-icon"
          />
        </a>
      </p>
    </AppForm>
    <template #actions>
      <AppButton
        v-if="keySet"
        variant="danger-quiet"
        label="Clear"
        :loading="removeKey.isPending.value"
        data-testid="ai-key-clear"
        @click="clear"
      />
      <AppButton
        variant="quiet"
        label="Check"
        :disable="!keySet && !draft.trim()"
        :loading="checking"
        data-testid="ai-key-check"
        @click="check"
      />
      <AppButton
        variant="quiet"
        label="Close"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        label="Save"
        :disable="!draft.trim()"
        :loading="writeKey.isPending.value"
        data-testid="ai-key-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.ai-key-dialog__page {
  margin: 0;
  color: var(--dp-text-muted);
}
.ai-key-dialog__page a {
  color: var(--dp-link);
  text-decoration: none;
}
.ai-key-dialog__page a:hover {
  text-decoration: underline;
}
.ai-key-dialog__page-icon {
  margin-inline-start: var(--dp-space-half);
  vertical-align: text-top;
}
</style>
