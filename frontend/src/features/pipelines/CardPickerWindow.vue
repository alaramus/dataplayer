<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, onMounted, ref } from "vue"

import type { CardRow } from "@/client"
import { useCatalogLoader } from "@/features/catalog/api"
import CatalogList from "@/features/catalog/CatalogList.vue"
import { ICONS, toListNodes } from "@/features/catalog/nodes"
import type { ListNode } from "@/features/catalog/nodes"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppBanner, AppButton, AppCheckbox, AppIconButton, AppInput, appIcons } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { rowId, TOP_ICON } from "./model"
import { isTicked, ticked, tickedAll, tickedNode, topRow, whereOf } from "./ticks"

/**
 * What a card holds, ticked in its connection's catalog (D175).
 *
 * Opened by a connection dropped on the canvas, and again by a card's
 * settings. Anything can be ticked: an object to take from, or a place — a
 * schema, a folder — for something to arrive in. A grouping is a level to
 * walk into here, not the filter it is in Data: a place has to be tickable.
 */
const props = defineProps<{
  connectorId: string
  connectionName: string
  /** What the card holds already; nothing for a card not made yet. */
  rows: CardRow[] | null
}>()

const emit = defineEmits<{
  done: [rows: CardRow[]]
  close: []
}>()

const loadChildren = useCatalogLoader()
const queryClient = useQueryClient()
// The levels walked into, below the top of the connection.
const trail = ref<{ id: string; label: string }[]>([])
const nodes = ref<ListNode[]>([])
const loading = ref(false)
const failure = ref("")
const refusal = ref("")
const filter = ref("")
const chosen = ref<CardRow[]>([...(props.rows ?? [])])

const names = computed(() => trail.value.map((step) => step.label))
const where = computed(() => [props.connectionName, ...names.value].join(" / "))
const shown = computed(() => {
  const needle = filter.value.trim().toLowerCase()
  return needle === "" ? nodes.value : nodes.value.filter((node) => node.label.toLowerCase().includes(needle))
})
const checked = computed(() =>
  shown.value.filter((node) => isTicked(chosen.value, node.id)).map((node) => node.id)
)
// The top of a connection is a place where it holds things and places rather
// than groupings: the top of personal storage is a folder, a database's is not.
const topIsPlace = computed(
  () => trail.value.length === 0 && !loading.value && failure.value === "" &&
    !nodes.value.some((node) => node.role === "group")
)
const topTicked = computed(() => isTicked(chosen.value, null))

async function show(nodeId: string | null): Promise<boolean> {
  loading.value = true
  failure.value = ""
  try {
    const page = await loadChildren(props.connectorId, nodeId)
    nodes.value = toListNodes(page.nodes)
    filter.value = ""
    return true
  } catch (cause) {
    failure.value = messageOf(cause, t("pipelines.card_picker.read_failed"))
    return false
  } finally {
    loading.value = false
  }
}

// Read as the connection is now: a pipeline's run may have written into it a
// moment ago, and the levels another screen keeps would still be fresh.
onMounted(() => {
  void queryClient
    .invalidateQueries({ queryKey: ["catalog", props.connectorId], refetchType: "none" })
    .then(() => show(null))
})

function apply(result: CardRow[] | string) {
  if (typeof result === "string") {
    refusal.value = result
    return
  }
  refusal.value = ""
  chosen.value = result
}

function toggle(id: string, on: boolean) {
  const node = nodes.value.find((one) => one.id === id)
  if (node !== undefined) apply(tickedNode(chosen.value, node, names.value, on))
}

async function open(node: ListNode) {
  if (node.role === "leaf") {
    toggle(node.id, !isTicked(chosen.value, node.id))
    return
  }
  if (await show(node.id)) trail.value = [...trail.value, { id: node.id, label: node.label }]
}

async function up() {
  const shorter = trail.value.slice(0, -1)
  if (await show(shorter.at(-1)?.id ?? null)) trail.value = shorter
}

function iconOf(row: CardRow): string {
  return row.kind == null ? TOP_ICON : ICONS[row.kind]
}
</script>

<template>
  <WindowDialog
    :model-value="true"
    :title="t('pipelines.card_picker.title', { name: connectionName })"
    :subtitle="t('pipelines.card_picker.subtitle')"
    size="form"
    sizing="stable"
    data-testid="card-picker"
    @update:model-value="emit('close')"
  >
    <div class="card-picker">
      <span
        class="card-picker__where"
        data-testid="card-picker-where"
      >{{ where }}</span>
      <AppInput
        v-model="filter"
        compact
        clearable
        :placeholder="t('pipelines.card_picker.filter')"
        :aria-label="t('pipelines.card_picker.filter_label')"
        autocomplete="off"
        data-testid="card-picker-filter"
      />
      <AppBanner
        v-if="failure"
        tone="error"
        data-testid="card-picker-error"
      >
        {{ failure }}
      </AppBanner>
      <label
        v-if="topIsPlace"
        class="card-picker__top"
      >
        <AppCheckbox
          :model-value="topTicked"
          dense
          :aria-label="t('pipelines.card_picker.tick_top', { name: connectionName })"
          data-testid="card-picker-top"
          @update:model-value="apply(ticked(chosen, topRow(connectionName), $event))"
        />
        <q-icon
          :name="TOP_ICON"
          size="var(--dp-icon-sm)"
        />
        <span>{{ t('pipelines.card_picker.top', { name: connectionName }) }}</span>
      </label>
      <CatalogList
        class="card-picker__list"
        :items="shown"
        :checked="checked"
        :loading="loading"
        :has-parent="trail.length > 0"
        @open="open"
        @up="up"
        @toggle="toggle"
        @toggle-all="apply(tickedAll(chosen, shown, names, $event))"
      />
      <div
        class="card-picker__chosen"
        data-testid="card-picker-chosen"
      >
        <span class="card-picker__count">
          {{ chosen.length === 0 ? t('pipelines.card_picker.nothing_ticked') : t('pipelines.card_picker.ticked', { n: chosen.length }) }}
        </span>
        <span
          v-if="refusal"
          class="card-picker__refusal"
          data-testid="card-picker-refusal"
        >{{ refusal }}</span>
        <ul class="card-picker__rows">
          <li
            v-for="row in chosen"
            :key="rowId(row.node_id)"
            class="card-picker__row"
            :data-testid="`card-picker-chosen-${row.label}`"
          >
            <q-icon
              :name="iconOf(row)"
              size="var(--dp-icon-sm)"
            />
            <span class="card-picker__label">{{ row.label }}</span>
            <span class="card-picker__place">{{ whereOf(row) }}</span>
            <AppIconButton
              :icon="appIcons.close"
              :tooltip="t('pipelines.card_picker.untick', { name: row.label })"
              @click="apply(ticked(chosen, row, false))"
            />
          </li>
        </ul>
      </div>
    </div>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        @click="emit('close')"
      />
      <AppButton
        :label="rows === null ? t('pipelines.card_picker.place') : t('catalog.common.save')"
        :disable="chosen.length === 0"
        data-testid="card-picker-done"
        @click="emit('done', chosen)"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.card-picker {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-3) var(--dp-space-4);
  box-sizing: border-box;
}
.card-picker__where {
  flex: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
.card-picker__top {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: 0 var(--dp-space-2);
  cursor: pointer;
}
.card-picker__list {
  flex: 1;
  min-height: 0;
}
.card-picker__chosen {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  max-height: 30%;
  min-height: 0;
  border-top: 1px solid var(--dp-border-faint);
  padding-top: var(--dp-space-1);
}
.card-picker__count {
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
}
.card-picker__refusal {
  font-size: var(--dp-font-size-sm);
  color: var(--dp-tone-warning-text);
}
.card-picker__rows {
  margin: 0;
  padding: 0;
  list-style: none;
  overflow: auto;
}
.card-picker__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}
.card-picker__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-picker__place {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
}
</style>
