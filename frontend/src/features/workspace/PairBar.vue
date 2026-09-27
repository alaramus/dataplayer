<script setup lang="ts">
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, ref } from "vue"

import { ConnectorsService } from "@/client"
import type { PasteOffer } from "@/client"
import CrossPaste from "@/features/catalog/CrossPaste.vue"
import type { ActionOutcome } from "@/features/catalog/actions"
import type { CrossPasteIntent } from "@/features/catalog/pasteOffers"
import { AppButton } from "@/shared/ui"
import { useSourceChangesStore } from "@/stores/sourceChanges"

import { settleSide, useCatalogSide } from "./catalogSides"
import type { CatalogSide } from "./catalogSides"
import { itemDetail, pasteIntentFor, usable } from "./pairs"
import type { PairCandidate } from "./pairs"

/**
 * What the ticks of the left catalog can become in the right one (D167).
 * One direction only: Swap sides turns it round. Every item is a Paste the
 * server offers; its button opens the windows that Paste would, and nothing
 * here names a kind.
 */
const props = defineProps<{ left: PairCandidate; right: PairCandidate }>()

const leftSide = useCatalogSide(() => props.left.panelId)
const rightSide = useCatalogSide(() => props.right.panelId)

const answer = useQuery({
  queryKey: computed(() => ["pair-offers", leftSide.value, rightSide.value]),
  enabled: computed(() => leftSide.value !== null && rightSide.value !== null),
  // Every new tick is a new question. Without the last answer held while it
  // is asked, the bar shrank to one line of "Checking" and back, and both
  // catalogs above it jumped with it.
  placeholderData: keepPreviousData,
  retry: false,
  queryFn: async () => {
    const left = leftSide.value
    const right = rightSide.value
    if (left === null || right === null) throw new Error("A catalog of the pair is not open")
    return (await ConnectorsService.pairOffers({
      body: { source: sideOf(left), destination: sideOf(right) },
    })).data
  },
})

function sideOf(side: CatalogSide) {
  return { connector_id: side.connectorId, place: side.place, ticked: side.ticked }
}

interface Item {
  offer: PasteOffer
  intent: CrossPasteIntent
  detail: string
}

const heading = computed(() => `${props.left.title} → ${props.right.title}`)

const items = computed<Item[]>(() => {
  const left = leftSide.value
  const right = rightSide.value
  if (left === null || right === null) return []
  return (answer.data.value?.offers ?? []).map((offer) => {
    const intent = pasteIntentFor(offer, left, right)
    return { offer, intent, detail: itemDetail(offer, intent) }
  })
})

const pasting = ref<CrossPasteIntent | null>(null)
let pastings = 0
const changes = useSourceChangesStore()
const queryClient = useQueryClient()

function run(intent: CrossPasteIntent) {
  // The items shown are the last answer until the new one arrives, a few
  // milliseconds; greying the buttons for that long would be the flicker again.
  if (pasting.value !== null || answer.isPlaceholderData.value) return
  pastings += 1
  pasting.value = intent
}

/**
 * The destination catalog re-reads as after any change to its connection, and
 * both let go of the ticks the paste was about — but for what it failed on.
 */
function afterPaste(outcome: ActionOutcome) {
  if (pasting.value !== null) changes.announce(pasting.value.destinationConnectorId)
  void queryClient.invalidateQueries({ queryKey: ["pair-offers"] })
  settle(outcome)
}

function settle(outcome: ActionOutcome | null) {
  settleSide(props.left.panelId, outcome)
  settleSide(props.right.panelId, outcome)
}
</script>

<template>
  <div
    class="pair-bar"
    data-testid="pair-bar"
  >
    <div class="pair-bar__heading">
      {{ heading }}
    </div>
    <div
      v-if="answer.isPending.value"
      class="pair-bar__note"
    >
      Checking what can be done
    </div>
    <div
      v-else-if="answer.isError.value"
      class="pair-bar__note"
    >
      Could not check these two connections
    </div>
    <div
      v-else-if="items.length === 0"
      class="pair-bar__note"
    >
      Nothing goes this way. Swap sides to go the other way.
    </div>
    <div
      v-for="entry in items"
      :key="entry.offer.kind"
      class="pair-bar__item"
      :data-testid="`pair-item-${entry.offer.kind}`"
    >
      <template v-if="usable(entry.offer)">
        <span class="pair-bar__detail">{{ entry.detail }}</span>
        <AppButton
          variant="secondary"
          size="sm"
          :label="entry.offer.title"
          :data-testid="`pair-run-${entry.offer.kind}`"
          @click="run(entry.intent)"
        />
      </template>
      <template v-else>
        <span class="pair-bar__detail pair-bar__detail--off">{{ entry.offer.title }}</span>
        <span class="pair-bar__reason">{{ entry.detail }}</span>
      </template>
    </div>
    <CrossPaste
      v-if="pasting"
      :key="pastings"
      :intent="pasting"
      @done="afterPaste"
      @started="settle(null)"
      @source-changed="changes.announce($event)"
      @close="pasting = null"
    />
  </div>
</template>

<style scoped>
.pair-bar {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  padding: var(--dp-space-2) var(--dp-space-3);
  border-top: 1px solid var(--dp-border);
  max-height: 40%;
  overflow: auto;
}
.pair-bar__heading {
  color: var(--dp-text-strong);
  font-weight: 500;
}
.pair-bar__note,
.pair-bar__reason {
  color: var(--dp-text-muted);
}
.pair-bar__item {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  min-height: var(--dp-form-control-height);
}
.pair-bar__detail {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pair-bar__detail--off {
  flex: 0 1 auto;
  color: var(--dp-text-muted);
}
</style>
