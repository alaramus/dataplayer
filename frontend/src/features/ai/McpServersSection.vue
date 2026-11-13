<script setup lang="ts">
import { ref } from "vue"

import type { McpServerPublic } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppBadge,
  AppBanner,
  AppButton,
  AppCheckbox,
  AppEmptyState,
  AppIconButton,
  AppSpinner,
  AppToggle,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"

import McpServerDialog from "./McpServerDialog.vue"
import { useDeleteMcpServer, useMcpServerTools, useMcpServers, useUpdateMcpServer } from "./api"

/**
 * Outside MCP servers whose tools the agent may call (D360, D361). A server's
 * tools are read when asked for, which is also how a person learns that it
 * answers; each can be switched off.
 */
const servers = useMcpServers()
const update = useUpdateMcpServer()
const remove = useDeleteMcpServer()
const toast = useToast()
const confirm = useConfirm()

const editing = ref<McpServerPublic | null>(null)
const open = ref(false)
const shown = ref<string | null>(null)
const tools = useMcpServerTools(() => shown.value)

function add() {
  editing.value = null
  open.value = true
}

function edit(server: McpServerPublic) {
  editing.value = server
  open.value = true
}

function toggleTools(server: McpServerPublic) {
  shown.value = shown.value === server.id ? null : server.id
}

async function change(server: McpServerPublic, body: { enabled?: boolean; tools_off?: string[] }) {
  try {
    await update.mutateAsync({ id: server.id, body })
  } catch (cause) {
    toast.error(messageOf(cause, t("ai.mcp_servers.save_failed")))
  }
}

async function switchTool(server: McpServerPublic, name: string, on: boolean) {
  const off = new Set(server.tools_off)
  if (on) off.delete(name)
  else off.add(name)
  await change(server, { tools_off: [...off] })
}

async function drop(server: McpServerPublic) {
  const sure = await confirm({
    title: t("ai.mcp_servers.remove_title"),
    message: t("ai.mcp_servers.remove_message", { name: server.name }),
    confirmLabel: t("ai.mcp_servers.remove_confirm"),
    danger: true,
  })
  if (!sure) return
  try {
    await remove.mutateAsync(server.id)
    if (shown.value === server.id) shown.value = null
  } catch (cause) {
    toast.error(messageOf(cause, t("ai.mcp_servers.remove_failed")))
  }
}
</script>

<template>
  <section
    class="mcp-servers"
    data-testid="mcp-servers"
  >
    <div class="mcp-servers__head">
      <div class="mcp-servers__what">
        <h3 class="mcp-servers__title">
          {{ t('ai.mcp_servers.title') }}
        </h3>
        <span class="dp-helper">{{ t('ai.mcp_servers.hint') }}</span>
      </div>
      <div>
        <AppButton
          size="sm"
          :icon="appIcons.add"
          :label="t('ai.mcp_servers.add')"
          data-testid="mcp-server-new"
          @click="add"
        />
      </div>
    </div>

    <AppSpinner v-if="servers.isLoading.value" />
    <AppEmptyState
      v-else-if="(servers.data.value ?? []).length === 0"
      :icon="appIcons.robot2"
      :text="t('ai.mcp_servers.empty')"
    />
    <div
      v-for="server in servers.data.value ?? []"
      :key="server.id"
      class="mcp-servers__item"
      :data-testid="`mcp-server-${server.name}`"
    >
      <div class="mcp-servers__row">
        <AppToggle
          :model-value="server.enabled"
          :data-testid="`mcp-server-switch-${server.name}`"
          @update:model-value="change(server, { enabled: $event })"
        />
        <div class="mcp-servers__facts">
          <span class="mcp-servers__name">{{ server.name }}</span>
          <span class="mcp-servers__line dp-helper">{{ server.url }}</span>
        </div>
        <AppBadge
          v-if="server.tools_off.length > 0"
          :label="t('ai.mcp_servers.tools_off', { n: server.tools_off.length })"
          tone="info"
        />
        <AppButton
          size="sm"
          variant="quiet"
          :label="shown === server.id ? t('ai.mcp_servers.hide_tools') : t('ai.mcp_servers.show_tools')"
          :data-testid="`mcp-server-tools-${server.name}`"
          @click="toggleTools(server)"
        />
        <AppIconButton
          :icon="appIcons.edit"
          :tooltip="t('ai.mcp_servers.edit')"
          :data-testid="`mcp-server-edit-${server.name}`"
          @click="edit(server)"
        />
        <AppIconButton
          :icon="appIcons.delete"
          :tooltip="t('ai.mcp_servers.remove')"
          variant="danger-quiet"
          :data-testid="`mcp-server-remove-${server.name}`"
          @click="drop(server)"
        />
      </div>
      <div
        v-if="shown === server.id"
        class="mcp-servers__tools"
        :data-testid="`mcp-server-tool-list-${server.name}`"
      >
        <AppSpinner v-if="tools.isFetching.value" />
        <AppBanner
          v-else-if="tools.isError.value"
          tone="error"
        >
          {{ messageOf(tools.error.value, t('ai.mcp_servers.tools_failed')) }}
        </AppBanner>
        <span
          v-else-if="(tools.data.value?.tools ?? []).length === 0"
          class="dp-helper"
        >{{ t('ai.mcp_servers.no_tools') }}</span>
        <div
          v-for="tool in tools.data.value?.tools ?? []"
          v-else
          :key="tool.name"
          class="mcp-servers__tool"
        >
          <AppCheckbox
            dense
            :model-value="!server.tools_off.includes(tool.name)"
            :label="tool.title ?? tool.name"
            :data-testid="`mcp-tool-${tool.name}`"
            @update:model-value="switchTool(server, tool.name, $event)"
          />
          <AppBadge
            :label="tool.read_only ? t('ai.mcp_servers.reads') : t('ai.mcp_servers.changes')"
            :tone="tool.read_only ? 'info' : 'warning'"
          />
          <span class="mcp-servers__line dp-helper">{{ tool.description }}</span>
        </div>
      </div>
    </div>

    <McpServerDialog
      v-model="open"
      :server="editing"
    />
  </section>
</template>

<style scoped>
/* A group of the agent's settings: as wide as the forms above it. */
.mcp-servers {
  display: flex;
  flex-direction: column;
  max-width: var(--dp-width-text);
  padding: var(--dp-space-4);
}
.mcp-servers__head {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--dp-space-2);
  padding-bottom: var(--dp-space-3);
}
.mcp-servers__what,
.mcp-servers__facts {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
}
.mcp-servers__facts {
  flex: 1;
  gap: var(--dp-space-half);
}
.mcp-servers__title {
  font-weight: 600;
}
.mcp-servers__name {
  font-weight: 500;
}
.mcp-servers__item + .mcp-servers__item {
  border-top: 1px solid var(--dp-border-faint);
}
.mcp-servers__row,
.mcp-servers__tool {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) 0;
}
.mcp-servers__tools {
  display: flex;
  flex-direction: column;
  padding: 0 0 var(--dp-space-2) var(--dp-space-5);
}
.mcp-servers__line {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
</style>
