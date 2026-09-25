<script setup lang="ts">
import { useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, ref } from "vue"

import { ConnectorsService } from "@/client"
import type { PasteOffer } from "@/client"
import CrossPaste from "@/features/catalog/CrossPaste.vue"
import type { CrossPasteIntent } from "@/features/catalog/pasteOffers"
import { AppButton } from "@/shared/ui"
import { useSourceChangesStore } from "@/stores/sourceChanges"

import { useCatalogSide } from "./catalogSides"
import type { CatalogSide } from "./catalogSides"
import { itemDetail, pasteIntentFor, usable } from "./pairs"
import type { PairCandidate } from "./pairs"

/**
 * What can be done between the two catalogs of a pair, both ways at once
 * (D167). Every item is a Paste the server offers; its button opens the
 * windows that Paste would, and nothing here names a kind.
 */
const props = defineProps<{ left: PairCandidate; right: PairCandidate }>()

const leftSide = useCatalogSide(() => props.left.panelId)
const rightSide = useCatalogSide(() => props.right.panelId)

const answer = useQuery({
  queryKey: computed(() => ["pair-offers", leftSide.value, rightSide.value]),
  enabled: computed(() => leftSide.value !== null && rightSide.value !== null),
  retry: false,
  queryFn: async () => {
    const left = leftSide.value
    const right = rightSide.value
    if (left === null || right === null) throw new Error("A catalog of the pair is not open")
    return (await ConnectorsService.pairOffers({
      body: { left: sideOf(left), right: sideOf(right) },
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

function itemsOf(offers: PasteOffer[], source: CatalogSide, destination: CatalogSide): Item[] {
  return offers.map((offer) => {
    const intent = pasteIntentFor(offer, source, destination)
    return { offer, intent, detail: itemDetail(offer, intent) }
  })
}

const directions = computed(() => {
  const left = leftSide.value
  const right = rightSide.value
  if (left === null || right === null) return []
  const offers = answer.data.value
  return [
    {
      key: "left",
      heading: `${props.left.title} → ${props.right.title}`,
      items: itemsOf(offers?.left_to_right ?? [], left, right),
    },
    {
      key: "right",
      heading: `${props.right.title} → ${props.left.title}`,
      items: itemsOf(offers?.right_to_left ?? [], right, left),
    },
  ]
})

const pasting = ref<CrossPasteIntent | null>(null)
let pastings = 0
const changes = useSourceChangesStore()
const queryClient = useQueryClient()

function run(intent: CrossPasteIntent) {
  if (pasting.value !== null) return
  pastings += 1
  pasting.value = intent
}

/** The destination catalog re-reads as after any change to its connection. */
function afterPaste() {
  if (pasting.value !== null) changes.announce(pasting.value.destinationConnectorId)
  void queryClient.invalidateQueries({ queryKey: ["pair-offers"] })
}
</script>

<template>
  <div
    class="pair-bar"
    data-testid="pair-bar"
  >
    <section
      v-for="direction in directions"
      :key="direction.key"
      class="pair-bar__direction"
      :data-testid="`pair-bar-${direction.key}`"
    >
      <div class="pair-bar__heading">
        {{ direction.heading }}
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
        v-else-if="direction.items.length === 0"
        class="pair-bar__note"
      >
        Nothing goes this way
      </div>
      <div
        v-for="entry in direction.items"
        :key="entry.offer.kind"
        class="pair-bar__item"
        :data-testid="`pair-item-${direction.key}-${entry.offer.kind}`"
      >
        <template v-if="usable(entry.offer)">
          <span class="pair-bar__detail">{{ entry.detail }}</span>
          <AppButton
            variant="secondary"
            size="sm"
            :label="entry.offer.title"
            :data-testid="`pair-run-${direction.key}-${entry.offer.kind}`"
            @click="run(entry.intent)"
          />
        </template>
        <template v-else>
          <span class="pair-bar__detail pair-bar__detail--off">{{ entry.offer.title }}</span>
          <span class="pair-bar__reason">{{ entry.detail }}</span>
        </template>
      </div>
    </section>
    <CrossPaste
      v-if="pasting"
      :key="pastings"
      :intent="pasting"
      @done="afterPaste"
      @source-changed="changes.announce($event)"
      @close="pasting = null"
    />
  </div>
</template>

<style scoped>
.pair-bar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  border-top: 1px solid var(--dp-border);
  max-height: 40%;
  overflow: auto;
}
.pair-bar__direction {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  padding: var(--dp-space-2) var(--dp-space-3);
}
.pair-bar__direction + .pair-bar__direction {
  border-left: 1px solid var(--dp-border);
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
