<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query"
import { computed, ref } from "vue"

import type { ColumnPair, Link, LinkEnd, LinkPlace, LinkRun, NewRelationColumn, PipelineRunPublic } from "@/client"
import CreateTableDialog from "@/features/grid/CreateTableDialog.vue"
import ImportDialog from "@/features/grid/ImportDialog.vue"
import { messageOf } from "@/shared/api/errors"
import { useNow } from "@/shared/freshness/useNow"
import { AppButton, AppIconButton, AppInput, AppSelect, AppSpinner, appIcons } from "@/shared/ui"

import { linkOffersKey, readLinkOffers } from "./api"
import type { LinkSide } from "./api"
import { CONFLICT_CHOICES, runWords, sentence, usable, withOffer } from "./links"
import type { EndNamer } from "./links"

/**
 * The panel below the canvas, on the link selected (D176): what it does and
 * where it comes in a run, the choices it runs by — the ones Paste asks — and
 * what it did in the run shown: the last (D177), or one pressed in the
 * history (D180).
 *
 * Every choice is the link's and is saved with the pipeline; the head's Run
 * runs what was saved, never what is on this screen.
 */
const props = defineProps<{
  link: Link
  from: LinkSide
  to: LinkSide
  name: EndNamer
  /** What an end is called on its own, which a table made from it is named after. */
  label: (end: LinkEnd) => string | null
  pipelineId: string
  /** The links making what either end is, as the offers are keyed by (D178). */
  chain: string
  /** Keeps the draft: the offers are the pipeline's as kept. */
  prepare: () => Promise<boolean>
  place: LinkPlace | undefined
  linkRun: LinkRun | undefined
  run: PipelineRunPublic | null | undefined
  /** The run shown is older than the last. */
  past: boolean
}>()

const emit = defineEmits<{
  change: [link: Link]
  /** Another operation chosen, and whether it makes something later links read. */
  operate: [link: Link, makes: boolean]
  remove: []
  close: []
}>()

const now = useNow()
const offers = useQuery({
  queryKey: computed(() => linkOffersKey(props.pipelineId, props.from, props.to, props.chain)),
  queryFn: async () => {
    await props.prepare()
    return readLinkOffers(props.pipelineId, props.from, props.to)
  },
  staleTime: 60_000,
  retry: false,
})
const choices = computed(() => usable(offers.data.value ?? []))
const offer = computed(() => (offers.data.value ?? []).find((one) => one.kind === props.link.kind))
const workflow = computed(() => offer.value?.workflow ?? "run")
const operations = computed(() => choices.value.map((one) => ({ label: one.title, value: one.kind })))
const conflicts = computed(() =>
  CONFLICT_CHOICES.filter((choice) => choice.value !== "replace" || offer.value?.can_replace !== false)
)
// The operation is not open to this person any more, or not for these rows.
const closed = computed(() =>
  offer.value !== undefined && !offer.value.available && offer.value.name_conflict !== true
    ? offer.value.reason ?? "This cannot run between these rows now"
    : null
)

function chooseOperation(kind: unknown) {
  const chosen = choices.value.find((one) => one.kind === kind)
  if (chosen !== undefined) emit("operate", withOffer(props.link, chosen), chosen.makes === true)
}

function rename(value: string | number | null) {
  const typed = String(value ?? "").trim()
  emit("change", { ...props.link, name: typed === "" ? null : typed.slice(0, 255) })
}

const tableOpen = ref(false)
const pairsOpen = ref(false)

function keepTable(made: { name: string; columns: NewRelationColumn[] }) {
  tableOpen.value = false
  emit("change", { ...props.link, name: made.name, columns: made.columns })
}

function keepPairs(paired: { columns: ColumnPair[] }) {
  pairsOpen.value = false
  emit("change", { ...props.link, columns: paired.columns })
}

const columnsWord = computed(() => {
  const count = props.link.columns?.length ?? 0
  if (count === 0) return workflow.value === "new-relation" ? "No table chosen yet" : "No columns paired yet"
  const columns = `${String(count)} ${count === 1 ? "column" : "columns"}`
  return workflow.value === "new-relation" ? `${props.link.name ?? "A new table"} with ${columns}` : `${columns} paired`
})
</script>

<template>
  <section
    class="link-panel"
    aria-label="The selected link"
    data-testid="link-panel"
  >
    <div class="link-panel__head">
      <span
        v-if="place"
        class="link-panel__number"
        :class="{ 'link-panel__number--caution': place.circle }"
        data-testid="link-panel-number"
      >{{ place.number }}</span>
      <strong
        class="link-panel__sentence"
        data-testid="link-panel-sentence"
      >{{ sentence(link, name) }}</strong>
      <AppIconButton
        :icon="appIcons.delete"
        tooltip="Remove this link"
        data-testid="link-panel-remove"
        @click="emit('remove')"
      />
      <AppIconButton
        :icon="appIcons.close"
        tooltip="Close"
        data-testid="link-panel-close"
        @click="emit('close')"
      />
    </div>

    <AppSpinner v-if="offers.isPending.value" />
    <p
      v-else-if="offers.isError.value"
      class="link-panel__problem"
    >
      {{ messageOf(offers.error.value, "What this link can do could not be read") }}
    </p>
    <div
      v-else
      class="link-panel__choices"
    >
      <AppSelect
        v-if="operations.length > 1"
        class="link-panel__field"
        :model-value="link.kind"
        :options="operations"
        label="Operation"
        compact
        data-testid="link-panel-operation"
        @update:model-value="chooseOperation"
      />
      <AppInput
        v-if="workflow === 'file-name'"
        class="link-panel__field"
        :model-value="link.name ?? ''"
        label="File name"
        :placeholder="offer?.suggested_name ?? undefined"
        compact
        autocomplete="off"
        data-testid="link-panel-name"
        @update:model-value="rename"
      />
      <AppSelect
        v-if="workflow === 'run' || workflow === 'file-name'"
        class="link-panel__field"
        :model-value="link.conflict ?? 'refuse'"
        :options="conflicts"
        label="If the name is taken"
        compact
        data-testid="link-panel-conflict"
        @update:model-value="emit('change', { ...link, conflict: $event as Link['conflict'] })"
      />
      <template v-if="workflow === 'new-relation' || workflow === 'into-relation'">
        <span
          class="link-panel__columns"
          data-testid="link-panel-columns"
        >{{ columnsWord }}</span>
        <AppButton
          variant="secondary"
          size="sm"
          :label="workflow === 'new-relation' ? 'Choose the table' : 'Pair columns'"
          data-testid="link-panel-choose-columns"
          @click="workflow === 'new-relation' ? (tableOpen = true) : (pairsOpen = true)"
        />
      </template>
    </div>

    <p
      v-if="place?.circle"
      class="link-panel__circle"
      data-testid="link-panel-circle"
    >
      {{ place.circle }}
    </p>
    <p
      class="link-panel__result"
      :class="{ 'link-panel__result--failed': closed !== null || linkRun?.outcome === 'failed' }"
      data-testid="link-panel-result"
    >
      {{ closed ?? runWords(linkRun, run, now, past) }}
    </p>
    <p
      v-if="!closed && (linkRun?.read || linkRun?.made)"
      class="link-panel__result"
      data-testid="link-panel-made"
    >
      {{ [linkRun?.read ? `Read ${linkRun.read}` : "", linkRun?.made ? `Made ${linkRun.made}` : ""].filter(Boolean).join(" · ") }}
    </p>

    <CreateTableDialog
      v-if="tableOpen && offer"
      :model-value="true"
      :source-title="label(link.source) ?? name(link.source)"
      :source-columns="offer.source_columns ?? []"
      :fixed-destination="{ connectorId: to.connectorId, parentNodeId: to.end.node_id ?? '', label: name(link.target) }"
      :running="false"
      error=""
      :kept="{ name: link.name ?? null, columns: link.columns ?? null }"
      action-label="Keep"
      @update:model-value="tableOpen = false"
      @run="keepTable"
    />
    <!-- A table a link makes has no node yet: the pairing is chosen all the
         same, only its preview has nothing to read (D178). -->
    <ImportDialog
      v-if="pairsOpen && offer"
      :model-value="true"
      :connector-id="to.connectorId"
      :node-id="to.end.node_id ?? ''"
      :target-columns="offer.target_columns ?? []"
      :target-label="name(link.target)"
      :source="{
        connectorId: from.connectorId,
        nodeId: from.end.node_id ?? '',
        label: name(link.source),
        columns: offer.source_columns ?? [],
      }"
      :running="false"
      error=""
      :kept="link.columns ?? null"
      action-label="Keep"
      @update:model-value="pairsOpen = false"
      @run="keepPairs"
    />
  </section>
</template>

<style scoped>
.link-panel {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-3);
  border-top: 1px solid var(--dp-border);
  background: var(--dp-surface);
}
.link-panel__head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
}
.link-panel__sentence {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.link-panel__number {
  flex: none;
  font-weight: 600;
}
.link-panel__number--caution,
.link-panel__circle {
  color: var(--dp-tone-warning-text);
}
.link-panel__choices {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--dp-space-2);
}
.link-panel__field {
  flex: 0 1 240px;
  min-width: 160px;
}
.link-panel__columns {
  color: var(--dp-text-muted);
}
.link-panel__circle,
.link-panel__result,
.link-panel__problem {
  margin: 0;
  color: var(--dp-text-muted);
  font-size: 12px;
}
.link-panel__result--failed {
  color: var(--dp-tone-warning-text);
}
</style>
