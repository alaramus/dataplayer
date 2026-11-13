<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { McpTokenCreated } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import { t } from "@/shared/i18n"
import { serverUrl } from "@/shared/servers/context"
import {
  AppBanner,
  AppButton,
  AppCopyButton,
  AppForm,
  AppInput,
  AppSelect,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useCreateMcpToken } from "./api"
import { EXPIRY_DAYS, claudeCommand, clientJson } from "./mcp"
import type { ExpiryDays } from "./mcp"

/**
 * Making a token for an outside agent (D358). The window asks a name, what
 * the token may do and how long it lasts, then shows the token itself — the
 * one time it is ever shown — with what a client is configured with.
 */
const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ "update:modelValue": [open: boolean] }>()

const toast = useToast()
const create = useCreateMcpToken()

type Policy = "read_only" | "full"
const name = ref("")
const policy = ref<Policy>("read_only")
const expiry = ref<ExpiryDays | "never">(90)
const error = ref("")
const made = ref<McpTokenCreated | null>(null)

const address = computed(() => serverUrl("/mcp"))
const policies = computed(() => [
  { label: t("preferences.mcp.read_only"), value: "read_only", description: t("preferences.mcp.read_only_hint") },
  { label: t("preferences.mcp.full"), value: "full", description: t("preferences.mcp.full_hint") },
])
const expiries = computed(() => [
  ...EXPIRY_DAYS.map((days) => ({ label: t("preferences.mcp.dialog.days", { count: days }), value: days })),
  { label: t("preferences.mcp.dialog.never"), value: "never" },
])
const command = computed(() => (made.value ? claudeCommand(address.value, made.value.token) : ""))
const json = computed(() => (made.value ? clientJson(address.value, made.value.token) : ""))

// A closed window forgets the token: it must not wait there for the next
// person at this screen.
watch(
  () => props.modelValue,
  (open) => {
    if (open) return
    name.value = ""
    policy.value = "read_only"
    expiry.value = 90
    error.value = ""
    made.value = null
  }
)

async function save() {
  if (name.value.trim() === "" || create.isPending.value) return
  error.value = ""
  try {
    made.value = await create.mutateAsync({
      name: name.value.trim(),
      policy: policy.value,
      expires_in_days: expiry.value === "never" ? null : expiry.value,
    })
  } catch (cause) {
    error.value = messageOf(cause, t("preferences.mcp.dialog.failed"))
  }
}

async function copy(text: string) {
  await copyText(text)
  toast.success(t("preferences.mcp.dialog.copied"))
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="made ? t('preferences.mcp.dialog.made_title') : t('preferences.mcp.dialog.title')"
    size="form"
    sizing="stable"
    data-testid="mcp-token-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm
      v-if="!made"
      layout="section"
    >
      <AppInput
        v-model="name"
        :label="t('preferences.mcp.dialog.name')"
        :hint="t('preferences.mcp.dialog.name_hint')"
        :error="error"
        autofocus
        data-testid="mcp-token-name"
      />
      <AppSelect
        :model-value="policy"
        :options="policies"
        :label="t('preferences.mcp.dialog.policy')"
        data-testid="mcp-token-policy"
        @update:model-value="policy = $event as Policy"
      />
      <AppSelect
        :model-value="expiry"
        :options="expiries"
        :label="t('preferences.mcp.dialog.expiry')"
        data-testid="mcp-token-expiry"
        @update:model-value="expiry = $event as ExpiryDays | 'never'"
      />
    </AppForm>
    <div
      v-else
      class="mcp-made"
    >
      <AppBanner tone="warning">
        {{ t('preferences.mcp.dialog.made_hint') }}
      </AppBanner>
      <div class="mcp-made__part">
        <span class="mcp-made__label">{{ t('preferences.mcp.dialog.token') }}</span>
        <div class="mcp-made__line">
          <code
            class="mcp-made__code"
            data-testid="mcp-token-value"
          >{{ made.token }}</code>
          <AppCopyButton
            :tooltip="t('preferences.mcp.dialog.copy_token')"
            data-testid="mcp-token-copy"
            @click="copy(made.token)"
          />
        </div>
      </div>
      <div class="mcp-made__part">
        <span class="mcp-made__label">{{ t('preferences.mcp.dialog.command') }}</span>
        <div class="mcp-made__line">
          <code class="mcp-made__code">{{ command }}</code>
          <AppCopyButton
            :tooltip="t('preferences.mcp.dialog.copy_command')"
            data-testid="mcp-token-copy-command"
            @click="copy(command)"
          />
        </div>
      </div>
      <div class="mcp-made__part">
        <span class="mcp-made__label">{{ t('preferences.mcp.dialog.json') }}</span>
        <div class="mcp-made__line">
          <pre class="mcp-made__code">{{ json }}</pre>
          <AppCopyButton
            :tooltip="t('preferences.mcp.dialog.copy_json')"
            @click="copy(json)"
          />
        </div>
      </div>
    </div>
    <template #actions>
      <template v-if="!made">
        <AppButton
          variant="quiet"
          :label="t('catalog.common.cancel')"
          @click="emit('update:modelValue', false)"
        />
        <AppButton
          :label="t('preferences.mcp.dialog.make')"
          :disable="name.trim() === ''"
          :loading="create.isPending.value"
          data-testid="mcp-token-save"
          @click="save"
        />
      </template>
      <AppButton
        v-else
        :label="t('preferences.mcp.dialog.done')"
        data-testid="mcp-token-done"
        @click="emit('update:modelValue', false)"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.mcp-made {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-4);
}
.mcp-made__part {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}
.mcp-made__label {
  font-weight: 500;
}
.mcp-made__line {
  display: flex;
  align-items: flex-start;
  gap: var(--dp-space-2);
}
.mcp-made__code {
  flex: 1;
  min-width: 0;
  margin: 0;
  padding: var(--dp-space-2);
  border: 1px solid var(--dp-field-border);
  border-radius: var(--dp-radius-control);
  background: var(--dp-field-surface);
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-mono);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
