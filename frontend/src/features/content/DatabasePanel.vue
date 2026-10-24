<script setup lang="ts">
import { computed, ref } from "vue"

import type { ContentRequest, DatabaseRelation } from "@/client"
import { useNodeActions, usePrepareConnectorAction } from "@/features/catalog/api"
import { formatSize } from "@/features/catalog/nodes"
import { useContent } from "@/features/content/api"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { errorKindOf, messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppBanner, AppButton, AppSpinner, AppTable, AppTooltip, useToast } from "@/shared/ui"
import type { TableColumns } from "@/shared/ui"

/**
 * A database file seen from a file source: the tables it holds (D262).
 *
 * What a person opens a `.db` to see, read from the file under the same guard
 * a connection to it uses. Rows are not read here: they belong to a
 * connection to the file.
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
}>()

const connectorId = computed(() => props.connectorId)
const request = computed<ContentRequest>(() => ({
  node_id: props.nodeId,
  representation: "database",
}))
const content = useContent(connectorId, request)
const errorKind = computed(() => errorKindOf(content.error.value))

const database = computed(() => {
  const value = content.data.value
  return value?.kind === "database" ? value : null
})
const error = computed(() =>
  content.isError.value ? messageOf(content.error.value, t("content.database.could_not_open")) : ""
)
const details = computed(() => {
  const value = database.value
  if (value === null) return ""
  return [
    value.engine,
    formatSize(value.size_bytes),
    t("content.database.relations", { n: value.total }, value.total),
  ].join(" · ")
})

const KIND_ICONS: Record<DatabaseRelation["kind"], string> = {
  table: "table_chart",
  view: "visibility",
  virtual: "travel_explore",
}

const columns = computed<TableColumns>(() => [
  { name: "name", label: t("content.database.name"), field: "name", align: "left", sortable: true },
  {
    name: "kind",
    label: t("content.database.kind"),
    field: (row: DatabaseRelation) => t(`content.database.kinds.${row.kind}`),
    align: "left",
    sortable: true,
  },
  {
    name: "rows",
    label: t("content.database.rows"),
    field: "row_estimate",
    align: "right",
    sortable: true,
    // Nothing counts rows: a table ANALYZE never saw says so.
    format: (value: number | null) =>
      value === null ? t("catalog.nodes.not_counted") : `~${String(value)}`,
  },
])

/**
 * A connection to this file, as a form to finish — the source's own action,
 * so who may make one and where is the server's answer (D262). Not drawn at
 * all where the action is not offered, as for somebody who only reads this
 * connection; drawn off, with the reason, where the file is out of reach.
 */
const nodeIds = computed(() => [props.nodeId])
const actions = useNodeActions(
  computed(() => props.connectorId),
  nodeIds
)
const connectAction = computed(
  () => actions.data.value?.find((action) => action.name === "connect_sqlite") ?? null
)
const prepare = usePrepareConnectorAction()
const workspace = useWorkspaceActions()
const toast = useToast()
const connecting = ref(false)

async function connect() {
  if (connectAction.value?.applicable !== true || connecting.value) return
  connecting.value = true
  try {
    const draft = await prepare.mutateAsync({
      connectorId: props.connectorId,
      name: "connect_sqlite",
      nodeId: props.nodeId,
    })
    workspace.createConnector(draft)
  } catch (cause) {
    toast.error(messageOf(cause, t("content.database.connect_failed")))
  } finally {
    connecting.value = false
  }
}

async function reload() {
  await content.refetch()
}

useReloadable(() => props.panelId, reload)
</script>

<template>
  <div class="database-panel">
    <div class="database-panel__head">
      <span
        class="database-panel__details"
        data-testid="database-details"
      >{{ details }}</span>
      <div class="database-panel__commands">
        <!-- The tooltip hangs off the wrapper: a disabled button takes no
             pointer events. -->
        <div
          v-if="connectAction !== null"
          data-testid="database-connect-wrap"
        >
          <AppButton
            variant="secondary"
            size="sm"
            :label="connectAction.title"
            :disable="!connectAction.applicable"
            :loading="connecting"
            data-testid="database-connect"
            @click="connect"
          />
          <AppTooltip v-if="!connectAction.applicable && connectAction.unavailable_reason">
            {{ connectAction.unavailable_reason }}
          </AppTooltip>
        </div>
        <PanelCommands
          :panel-id="panelId"
          :reveal="{ connectorId, nodeId, label: title }"
        />
      </div>
    </div>

    <SourceErrorBanner
      v-if="error"
      :connector-id="connectorId"
      :error-kind="errorKind"
      data-testid="content-error"
    >
      {{ error }}
    </SourceErrorBanner>
    <AppSpinner v-else-if="content.isPending.value" />
    <template v-else-if="database !== null">
      <AppBanner
        v-if="database.total > database.relations.length"
        tone="info"
        data-testid="database-cut"
      >
        {{ t("content.database.cut", { shown: database.relations.length, total: database.total }) }}
      </AppBanner>
      <AppTable
        class="database-panel__table"
        :rows="database.relations"
        :columns="columns"
        row-key="name"
        compact
        sticky
        :paged="false"
        :empty-text="t('content.database.empty')"
        data-testid="database-relations"
      >
        <template #body-cell-name="cell">
          <q-td :props="cell">
            <span class="database-panel__name">
              <q-icon
                :name="KIND_ICONS[(cell.row as DatabaseRelation).kind]"
                size="var(--dp-icon-sm)"
              />
              {{ cell.value }}
            </span>
          </q-td>
        </template>
      </AppTable>
    </template>
  </div>
</template>

<style scoped>
.database-panel {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
}
.database-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
}
/* On the words and not on the head: a flat button takes its colour from what
   contains it, and the commands beside this line are not disabled. */
.database-panel__details {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
}
.database-panel__commands {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
}
.database-panel__table {
  flex: 1;
  min-height: 0;
}
.database-panel__name {
  display: inline-flex;
  align-items: center;
  gap: var(--dp-space-2);
}
</style>
