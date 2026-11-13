<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { McpServerPublic } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppButton, AppCheckbox, AppForm, AppIconButton, AppInput, AppToggle, appIcons } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useCreateMcpServer, useUpdateMcpServer } from "./api"
import { createBody, formOf, updateBody } from "./mcpServers"
import type { ServerForm } from "./mcpServers"

/**
 * Adding or changing an outside MCP server (D360). Secrets are typed, never
 * shown: a saved token or header says it is set, and an empty field keeps it.
 */
const props = defineProps<{ modelValue: boolean; server: McpServerPublic | null }>()
const emit = defineEmits<{
  "update:modelValue": [open: boolean]
  saved: [server: McpServerPublic]
}>()

const create = useCreateMcpServer()
const update = useUpdateMcpServer()
const form = ref<ServerForm>(formOf(null))
const error = ref("")
const pending = computed(() => create.isPending.value || update.isPending.value)
const ready = computed(() => form.value.name.trim() !== "" && form.value.url.trim() !== "")

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    form.value = formOf(props.server)
    error.value = ""
  },
  { immediate: true }
)

function addHeader() {
  form.value.headers.push({ name: "", value: "" })
}

function removeHeader(index: number) {
  form.value.headers.splice(index, 1)
}

function kept(name: string): boolean {
  return props.server?.header_names.includes(name.trim()) ?? false
}

async function save() {
  if (!ready.value || pending.value) return
  error.value = ""
  try {
    const saved = props.server
      ? await update.mutateAsync({ id: props.server.id, body: updateBody(form.value, props.server) })
      : await create.mutateAsync(createBody(form.value))
    emit("saved", saved)
    emit("update:modelValue", false)
  } catch (cause) {
    error.value = messageOf(cause, t("ai.mcp_servers.save_failed"))
  }
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="server ? t('ai.mcp_servers.edit_title', { name: server.name }) : t('ai.mcp_servers.new_title')"
    size="form"
    sizing="stable"
    data-testid="mcp-server-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppInput
        v-model="form.name"
        :label="t('ai.mcp_servers.name')"
        :error="error"
        autofocus
        data-testid="mcp-server-name"
      />
      <AppInput
        v-model="form.url"
        :label="t('ai.mcp_servers.url')"
        :hint="t('ai.mcp_servers.url_hint')"
        monospace
        data-testid="mcp-server-url"
      />
      <AppInput
        v-model="form.token"
        type="password"
        :label="t('ai.mcp_servers.token')"
        :hint="server?.has_token ? t('ai.mcp_servers.token_kept') : t('ai.mcp_servers.token_hint')"
        data-testid="mcp-server-token"
      />
      <AppCheckbox
        v-if="server?.has_token && form.token === ''"
        v-model="form.clearToken"
        :label="t('ai.mcp_servers.clear_token')"
        data-testid="mcp-server-clear-token"
      />
      <div class="mcp-headers">
        <span class="mcp-headers__title">{{ t('ai.mcp_servers.headers') }}</span>
        <div
          v-for="(row, index) in form.headers"
          :key="index"
          class="mcp-headers__row"
        >
          <AppInput
            v-model="row.name"
            :label="t('ai.mcp_servers.header_name')"
            :data-testid="`mcp-server-header-name-${index}`"
          />
          <AppInput
            v-model="row.value"
            type="password"
            :label="t('ai.mcp_servers.header_value')"
            :placeholder="kept(row.name) ? t('ai.mcp_servers.header_kept') : ''"
            :data-testid="`mcp-server-header-value-${index}`"
          />
          <AppIconButton
            :icon="appIcons.delete"
            :tooltip="t('ai.mcp_servers.remove_header')"
            variant="danger-quiet"
            @click="removeHeader(index)"
          />
        </div>
        <div>
          <AppButton
            size="sm"
            variant="quiet"
            :icon="appIcons.add"
            :label="t('ai.mcp_servers.add_header')"
            data-testid="mcp-server-add-header"
            @click="addHeader"
          />
        </div>
      </div>
      <AppToggle
        v-model="form.enabled"
        :label="t('ai.mcp_servers.enabled')"
        data-testid="mcp-server-enabled"
      />
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="t('ai.mcp_servers.save')"
        :disable="!ready"
        :loading="pending"
        data-testid="mcp-server-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.mcp-headers {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}
.mcp-headers__title {
  font-weight: 500;
}
.mcp-headers__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: var(--dp-space-2);
  align-items: end;
}
</style>
