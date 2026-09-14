<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { AgentHost, AgentKey, AgentPublic, ConnectorReporting } from "@/client"
import { adapterIcon } from "@/features/connectors/adapters"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import { serverUrl } from "@/shared/servers/context"
import {
  AppButton,
  AppCopyButton,
  AppIconButton,
  AppInput,
  AppSection,
  AppSelect,
  AppTable,
  AppToggle,
  AppTooltip,
  useConfirm,
  useToast,
} from "@/shared/ui"
import type { TableColumns } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { hardwareWording, hostDetailWording, systemWording, upWording } from "./hostFacts"

import { composeSnippet, lastHeardWording } from "./agentSnippet"
import {
  readAgentKey,
  useAgents,
  useCreateAgent,
  useDeleteAgent,
  useHosts,
  usePurgeAgent,
  useReporting,
  useRotateAgentKey,
  useUpdateReporting,
} from "./api"

/**
 * What reports metrics: the agents of the person looking — registering one
 * hands out the key it signs under, and the Compose file to start it with —,
 * the hosts those agents report and what each is (D130), and the connections
 * they may see whose type reports about itself, switched on by their owners
 * (D128).
 */
const open = defineModel<boolean>({ required: true })

const toast = useToast()
const confirm = useConfirm()
const agents = useAgents(open)
const creating = useCreateAgent()
const rotating = useRotateAgentKey()
const deleting = useDeleteAgent()
const purging = usePurgeAgent()
const hosts = useHosts(open)

// One agent key may report several hosts, and two agents one host name.
const hostRows = computed(() => (hosts.data.value ?? []).map((host) => ({ ...host, key: `${host.agent_id}/${host.host}` })))

const hostColumns: TableColumns = [
  { name: "host", label: "Host", field: "host", align: "left" },
  { name: "agent", label: "Agent", field: "agent_name", align: "left" },
  { name: "system", label: "System", field: (row: AgentHost) => systemWording(row), align: "left" },
  { name: "hardware", label: "Hardware", field: (row: AgentHost) => hardwareWording(row), align: "left" },
  { name: "up", label: "Up for", field: "booted_at", align: "left" },
  { name: "heard", label: "Last heard", field: "last_seen", align: "left" },
]

const reporting = useReporting(open)
const updating = useUpdateReporting()

const INTERVALS: { value: ConnectorReporting["interval_seconds"]; label: string }[] = [
  { value: 15, label: "Every 15 s" },
  { value: 30, label: "Every 30 s" },
  { value: 60, label: "Every minute" },
  { value: 300, label: "Every 5 minutes" },
]

const connectionColumns: TableColumns = [
  { name: "name", label: "Connection", field: "name", align: "left" },
  { name: "reports", label: "Reports", field: "enabled", align: "left" },
  { name: "interval", label: "How often", field: "interval_seconds", align: "left" },
  { name: "heard", label: "Last reported", field: "last_heard_at", align: "left" },
]

async function report(row: ConnectorReporting, patch: Partial<Pick<ConnectorReporting, "enabled" | "interval_seconds">>) {
  try {
    await updating.mutateAsync({
      connectorId: row.connector_id,
      body: { enabled: patch.enabled ?? row.enabled, interval_seconds: patch.interval_seconds ?? row.interval_seconds },
    })
  } catch (cause) {
    toast.error(messageOf(cause, "Reporting could not be changed"))
  }
}

const newName = ref("")
const shown = ref<AgentKey | null>(null)
const hostname = ref("")
const now = ref(Date.now())

watch(open, (isOpen) => {
  if (!isOpen) shown.value = null
  now.value = Date.now()
})

const columns: TableColumns = [
  { name: "name", label: "Agent", field: "name", align: "left" },
  { name: "heard", label: "Last heard", field: "last_heard_at", align: "left" },
  { name: "actions", label: "", field: "id", align: "right" },
]

const rows = computed(() => agents.data.value ?? [])

const snippet = computed(() => {
  if (shown.value === null) return ""
  return composeSnippet({
    key: shown.value.key,
    port: shown.value.udp_port,
    serverHost: new URL(serverUrl("/")).hostname,
    hostname: hostname.value,
  })
})

function show(answer: AgentKey) {
  shown.value = answer
  hostname.value = ""
}

async function register() {
  const name = newName.value.trim()
  if (name === "") return
  try {
    show(await creating.mutateAsync(name))
    newName.value = ""
  } catch (cause) {
    toast.error(messageOf(cause, "The agent could not be registered"))
  }
}

async function showKey(agent: AgentPublic) {
  try {
    show(await readAgentKey(agent.id))
  } catch (cause) {
    toast.error(messageOf(cause, "The key could not be read"))
  }
}

async function rotate(agent: AgentPublic) {
  const sure = await confirm({
    title: "Issue a new key?",
    message: `What ${agent.name} sends signed with its current key will be dropped from now on.`,
    confirmLabel: "Issue a new key",
  })
  if (!sure) return
  try {
    show(await rotating.mutateAsync(agent.id))
  } catch (cause) {
    toast.error(messageOf(cause, "A new key could not be issued"))
  }
}

async function purge(agent: AgentPublic) {
  const sure = await confirm({
    title: "Delete every sample?",
    message: `Everything ${agent.name} has reported will be deleted. The agent stays registered.`,
    confirmLabel: "Delete samples",
    danger: true,
  })
  if (!sure) return
  try {
    toast.success((await purging.mutateAsync(agent.id)).message)
  } catch (cause) {
    toast.error(messageOf(cause, "The samples could not be deleted"))
  }
}

async function remove(agent: AgentPublic) {
  const sure = await confirm({
    title: "Remove this agent?",
    message: `What is sent signed with its key will be dropped. What ${agent.name} already reported stays until it expires.`,
    confirmLabel: "Remove",
    danger: true,
  })
  if (!sure) return
  try {
    await deleting.mutateAsync(agent.id)
    if (shown.value?.agent.id === agent.id) shown.value = null
  } catch (cause) {
    toast.error(messageOf(cause, "The agent could not be removed"))
  }
}

async function copy(text: string, what: string) {
  try {
    await copyText(text)
    toast.success(`${what} copied`)
  } catch {
    toast.error(`${what} could not be copied`)
  }
}
</script>

<template>
  <WindowDialog
    v-model="open"
    title="Sources"
    subtitle="Agents that report a host, and connections that report about themselves"
    size="lg"
    data-testid="agents-dialog"
  >
    <AppSection gutter>
      <div class="agents__register">
        <AppInput
          v-model="newName"
          label="Name of a new agent"
          compact
          data-testid="agent-name"
          @keydown.enter="register"
        />
        <AppButton
          label="Register"
          icon="add"
          :loading="creating.isPending.value"
          :disable="newName.trim() === ''"
          data-testid="agent-register"
          @click="register"
        />
      </div>

      <AppTable
        :rows="rows"
        :columns="columns"
        row-key="id"
        :loading="agents.isLoading.value"
        empty-text="No agents yet"
        compact
        :paged="false"
        data-testid="agents-table"
      >
        <template #body-cell-heard="cellProps">
          <q-td :props="cellProps">
            {{ lastHeardWording(cellProps.row.last_heard_at, now) }}
          </q-td>
        </template>
        <template #body-cell-actions="cellProps">
          <q-td :props="cellProps">
            <AppIconButton
              icon="key"
              tooltip="Show the key and how to start the agent"
              :data-testid="`agent-key-${cellProps.row.name}`"
              @click="showKey(cellProps.row)"
            />
            <AppIconButton
              icon="autorenew"
              tooltip="Issue a new key"
              @click="rotate(cellProps.row)"
            />
            <AppIconButton
              icon="delete_sweep"
              tooltip="Delete every sample it reported"
              variant="danger-quiet"
              @click="purge(cellProps.row)"
            />
            <AppIconButton
              icon="delete"
              tooltip="Remove this agent"
              variant="danger-quiet"
              @click="remove(cellProps.row)"
            />
          </q-td>
        </template>
      </AppTable>
    </AppSection>

    <AppSection
      divided
      gutter
    >
      <span>Hosts</span>
      <AppTable
        :rows="hostRows"
        :columns="hostColumns"
        row-key="key"
        :loading="hosts.isLoading.value"
        empty-text="No agent has reported a host yet"
        compact
        :paged="false"
        data-testid="hosts-table"
      >
        <template #body-cell-host="cellProps">
          <q-td :props="cellProps">
            {{ cellProps.row.host }}
            <AppTooltip>{{ hostDetailWording(cellProps.row) }}</AppTooltip>
          </q-td>
        </template>
        <template #body-cell-up="cellProps">
          <q-td :props="cellProps">
            {{ upWording(cellProps.row, now) }}
          </q-td>
        </template>
        <template #body-cell-heard="cellProps">
          <q-td :props="cellProps">
            {{ lastHeardWording(cellProps.row.last_seen, now) }}
          </q-td>
        </template>
      </AppTable>
    </AppSection>

    <AppSection
      divided
      gutter
    >
      <span>Connections</span>
      <AppTable
        :rows="reporting.data.value ?? []"
        :columns="connectionColumns"
        row-key="connector_id"
        :loading="reporting.isLoading.value"
        empty-text="No connection you can see reports metrics"
        compact
        :paged="false"
        data-testid="reporting-table"
      >
        <template #body-cell-name="cellProps">
          <q-td :props="cellProps">
            <q-icon
              :name="adapterIcon(cellProps.row.adapter_type)"
              size="16px"
            />
            {{ cellProps.row.name }}
          </q-td>
        </template>
        <template #body-cell-reports="cellProps">
          <q-td :props="cellProps">
            <span class="agents__slot">
              <AppToggle
                :model-value="cellProps.row.enabled"
                :disable="!cellProps.row.may_change || updating.isPending.value"
                :aria-label="`Report metrics of ${cellProps.row.name}`"
                :data-testid="`reporting-${cellProps.row.name}`"
                @update:model-value="(value) => report(cellProps.row, { enabled: value })"
              />
              <AppTooltip v-if="!cellProps.row.may_change">Only the owner of this connection switches its reporting on</AppTooltip>
            </span>
          </q-td>
        </template>
        <template #body-cell-interval="cellProps">
          <q-td :props="cellProps">
            <AppSelect
              :model-value="cellProps.row.interval_seconds"
              :options="INTERVALS"
              :disable="!cellProps.row.may_change"
              compact
              aria-label="How often"
              @update:model-value="(value) => report(cellProps.row, { interval_seconds: value as ConnectorReporting['interval_seconds'] })"
            />
          </q-td>
        </template>
        <template #body-cell-heard="cellProps">
          <q-td :props="cellProps">
            {{ lastHeardWording(cellProps.row.last_heard_at, now) }}
          </q-td>
        </template>
      </AppTable>
    </AppSection>

    <AppSection
      v-if="shown"
      divided
      gutter
      data-testid="agent-key-panel"
    >
      <div class="agents__key">
        <span>Key of {{ shown.agent.name }}</span>
        <code data-testid="agent-key">{{ shown.key }}</code>
        <AppCopyButton
          tooltip="Copy the key"
          @click="copy(shown.key, 'The key')"
        />
      </div>
      <AppInput
        v-model="hostname"
        label="Host name it reports as"
        hint="Empty: the name the host has"
        compact
      />
      <div class="agents__snippet">
        <pre data-testid="agent-snippet">{{ snippet }}</pre>
        <AppCopyButton
          tooltip="Copy the Compose file"
          @click="copy(snippet, 'The Compose file')"
        />
      </div>
    </AppSection>

    <template #actions>
      <AppButton
        variant="quiet"
        label="Close"
        @click="open = false"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.agents__slot {
  display: inline-flex;
}

.agents__register,
.agents__key {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}

.agents__snippet {
  display: flex;
  align-items: flex-start;
  gap: var(--dp-space-2);
}

.agents__snippet pre {
  flex: 1;
  margin: 0;
  padding: var(--dp-space-2);
  overflow-x: auto;
  border: 1px solid var(--dp-border-faint);
  border-radius: var(--dp-radius-control);
}
</style>
