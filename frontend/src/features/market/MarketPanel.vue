<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue"

import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { currentLanguage, t } from "@/shared/i18n"
import { formatTime } from "@/shared/i18n/format"
import { serverUrl } from "@/shared/servers/context"
import { AppBanner, AppSelect, AppSpinner } from "@/shared/ui"
import { useAuthStore } from "@/stores/auth"

import MarketChart from "./MarketChart.vue"
import { applyRows, bookOf, candlesOf, dayOf, falling, shown, tradesOf } from "./model"
import type { Parts } from "./model"
import { openWatchLink } from "./watchLink"
import type { WatchLink, WatchState } from "./watchLink"

/**
 * A symbol watched live: its day, its candles over their volume, the book
 * and the tape (D323). Everything arrives as rows over a watch socket of its
 * own; a new interval is a new socket, which starts with the symbol as it
 * stands.
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
}>()

const parts = shallowRef<Parts>({})
const state = ref<WatchState>({ kind: "connecting" })
const interval = ref<string | null>(null)
const intervals = ref<string[]>([])
let link: WatchLink | null = null

function socketUrl(): string {
  const url = new URL(serverUrl("/api/v1/watch"))
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  // A browser cannot set a socket's headers, so the language travels here (D226).
  url.searchParams.set("lang", currentLanguage())
  return url.toString()
}

function watchNode() {
  link?.close()
  parts.value = {}
  const token = useAuthStore().token
  if (token === null) {
    state.value = { kind: "refused", code: "unauthenticated", message: t("terminals.notice.sign_in") }
    return
  }
  link = openWatchLink({
    url: socketUrl(),
    token,
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    interval: interval.value,
    onRows: (rows) => {
      parts.value = applyRows(parts.value, rows)
    },
    onState: (next) => {
      state.value = next
      if (next.kind === "open") {
        intervals.value = next.intervals
        interval.value = next.interval
      }
    },
  })
}

watchNode()
onBeforeUnmount(() => link?.close())

function chooseInterval(value: unknown) {
  if (typeof value !== "string" || value === interval.value) return
  interval.value = value
  watchNode()
}

// The language is chosen when the socket opens; a change of it opens another.
watch(currentLanguage, watchNode)

const day = computed(() => dayOf(parts.value))
const candles = computed(() => candlesOf(parts.value))
const book = computed(() => bookOf(parts.value))
// The levels drawn of each side, best first: enough to see the spread and
// the walls near it, and the tape below keeps room to read.
const BOOK_SHOWN = 12
const asksTopDown = computed(() => book.value.asks.slice(0, BOOK_SHOWN).reverse())
const bidsShown = computed(() => book.value.bids.slice(0, BOOK_SHOWN))
const trades = computed(() => tradesOf(parts.value))
const down = computed(() => falling(day.value?.change ?? null))

const problem = computed(() => {
  const now = state.value
  if (now.kind === "refused" || now.kind === "ended") return now.message
  return ""
})
const status = computed(() => {
  const now = state.value
  if (now.kind === "connecting") return t("content.market.connecting")
  if (now.kind === "lost") {
    return t("content.market.lost", { seconds: Math.ceil(now.retryInMs / 1000) })
  }
  if (now.kind === "open") return t("content.market.live")
  return ""
})

function time(text: string): string {
  const at = new Date(text)
  return Number.isNaN(at.getTime())
    ? text
    : formatTime(at, { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}
</script>

<template>
  <div
    class="market-panel"
    data-testid="market-panel"
  >
    <div class="market-panel__head">
      <div
        class="market-panel__day"
        data-testid="market-day"
      >
        <span
          class="market-panel__price"
          :class="down ? 'market-panel__down' : 'market-panel__up'"
          data-testid="market-price"
        >{{ shown(day?.lastPrice ?? null) }}</span>
        <span class="market-panel__fact">
          <span class="market-panel__label">{{ t("content.market.change") }}</span>
          <span :class="down ? 'market-panel__down' : 'market-panel__up'">
            {{ shown(day?.change ?? null) }} ({{ shown(day?.changePercent ?? null) }}%)
          </span>
        </span>
        <span class="market-panel__fact">
          <span class="market-panel__label">{{ t("content.market.high") }}</span>
          {{ shown(day?.high ?? null) }}
        </span>
        <span class="market-panel__fact">
          <span class="market-panel__label">{{ t("content.market.low") }}</span>
          {{ shown(day?.low ?? null) }}
        </span>
        <span class="market-panel__fact">
          <span class="market-panel__label">{{ t("content.market.volume") }}</span>
          {{ shown(day?.volume ?? null) }}
        </span>
        <span class="market-panel__fact">
          <span class="market-panel__label">{{ t("content.market.quote_volume") }}</span>
          {{ shown(day?.quoteVolume ?? null) }}
        </span>
      </div>
      <div class="market-panel__commands">
        <span
          class="market-panel__status"
          data-testid="market-status"
        >{{ status }}</span>
        <AppSelect
          v-if="intervals.length > 0"
          :model-value="interval"
          :options="intervals"
          compact
          :aria-label="t('content.market.interval')"
          data-testid="market-interval"
          @update:model-value="chooseInterval"
        />
        <PanelCommands
          :panel-id="panelId"
          :reveal="{ connectorId, nodeId, label: title }"
        />
      </div>
    </div>

    <AppBanner
      v-if="problem"
      tone="error"
      data-testid="market-error"
    >
      {{ problem }}
    </AppBanner>
    <AppSpinner v-else-if="candles.length === 0 && state.kind !== 'lost'" />

    <div
      v-show="!problem && candles.length > 0"
      class="market-panel__body"
    >
      <div class="market-panel__chart">
        <MarketChart :candles="candles" />
      </div>

      <div class="market-panel__side">
        <div
          class="market-panel__book"
          data-testid="market-book"
        >
          <div class="market-panel__title">
            {{ t("content.market.book") }}
          </div>
          <div class="market-panel__row market-panel__row--head">
            <span class="market-panel__cell">{{ t("content.market.price") }}</span>
            <span class="market-panel__cell">{{ t("content.market.quantity") }}</span>
            <span class="market-panel__cell">{{ t("content.market.total") }}</span>
          </div>
          <div class="market-panel__levels">
            <div
              v-for="level in asksTopDown"
              :key="`ask-${level.price}`"
              class="market-panel__row"
              data-testid="market-ask"
            >
              <span
                class="market-panel__depth market-panel__depth--ask"
                :style="{ width: `${level.depth * 100}%` }"
              />
              <span class="market-panel__cell market-panel__down">{{ shown(level.price) }}</span>
              <span class="market-panel__cell">{{ shown(level.quantity) }}</span>
              <span class="market-panel__cell">{{ shown(level.cumulative) }}</span>
            </div>
          </div>
          <div
            class="market-panel__spread"
            :class="down ? 'market-panel__down' : 'market-panel__up'"
          >
            {{ shown(day?.lastPrice ?? null) }}
          </div>
          <div class="market-panel__levels">
            <div
              v-for="level in bidsShown"
              :key="`bid-${level.price}`"
              class="market-panel__row"
              data-testid="market-bid"
            >
              <span
                class="market-panel__depth market-panel__depth--bid"
                :style="{ width: `${level.depth * 100}%` }"
              />
              <span class="market-panel__cell market-panel__up">{{ shown(level.price) }}</span>
              <span class="market-panel__cell">{{ shown(level.quantity) }}</span>
              <span class="market-panel__cell">{{ shown(level.cumulative) }}</span>
            </div>
          </div>
        </div>

        <div
          class="market-panel__tape"
          data-testid="market-trades"
        >
          <div class="market-panel__title">
            {{ t("content.market.trades") }}
          </div>
          <div class="market-panel__row market-panel__row--head">
            <span class="market-panel__cell">{{ t("content.market.price") }}</span>
            <span class="market-panel__cell">{{ t("content.market.quantity") }}</span>
            <span class="market-panel__cell">{{ t("content.market.time") }}</span>
          </div>
          <div class="market-panel__trades dp-panel-scroll">
            <div
              v-for="trade in trades"
              :key="trade.id"
              class="market-panel__row"
              data-testid="market-trade"
            >
              <span
                class="market-panel__cell"
                :class="trade.sold ? 'market-panel__down' : 'market-panel__up'"
              >{{ shown(trade.price) }}</span>
              <span class="market-panel__cell">{{ shown(trade.quantity) }}</span>
              <span class="market-panel__cell market-panel__muted">{{ time(trade.time) }}</span>
            </div>
            <div
              v-if="trades.length === 0"
              class="market-panel__muted"
            >
              {{ t("content.market.nothing_yet") }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.market-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
  gap: var(--dp-space-1);
}
.market-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-3);
  min-height: var(--dp-toolbar-height);
  padding: 0 var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
}
.market-panel__day {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--dp-space-1) var(--dp-space-4);
  min-width: 0;
  font-variant-numeric: tabular-nums;
}
.market-panel__price {
  font-size: var(--dp-font-size-lg);
  font-weight: 600;
}
.market-panel__fact {
  display: inline-flex;
  gap: var(--dp-space-1);
  font-size: var(--dp-font-size-sm);
  white-space: nowrap;
}
.market-panel__label,
.market-panel__muted,
.market-panel__status {
  color: var(--dp-text-muted);
}
.market-panel__status {
  font-size: var(--dp-font-size-xs);
  white-space: nowrap;
}
.market-panel__commands {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  flex: none;
}
.market-panel__up {
  color: var(--dp-content-success);
}
.market-panel__down {
  color: var(--dp-content-error);
}
.market-panel__body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--dp-side-column-width);
  gap: var(--dp-space-2);
}
.market-panel__chart {
  min-width: 0;
  min-height: 0;
}
/* The book above the tape: the chart keeps the width, and both read down. */
.market-panel__side {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  min-height: 0;
  font-size: var(--dp-font-size-xs);
  font-variant-numeric: tabular-nums;
  border-left: 1px solid var(--dp-border-faint);
  padding-left: var(--dp-space-2);
}
.market-panel__title {
  font-size: var(--dp-font-size-sm);
  font-weight: 600;
  padding-bottom: var(--dp-space-1);
}
.market-panel__levels {
  display: flex;
  flex-direction: column;
}
.market-panel__row {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--dp-space-1);
  line-height: var(--dp-line-height-xs);
}
/* Positioned, so they paint over the depth drawn before them. */
.market-panel__cell {
  position: relative;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.market-panel__cell + .market-panel__cell {
  text-align: end;
}
.market-panel__row--head {
  color: var(--dp-text-muted);
}
/* Drawn behind the row from its far end, as deep as that level reaches. */
.market-panel__depth {
  position: absolute;
  inset-block: 0;
  inset-inline-end: 0;
}
.market-panel__depth--ask {
  background: var(--dp-tone-error-wash);
}
.market-panel__depth--bid {
  background: var(--dp-tone-success-wash);
}
.market-panel__spread {
  padding: var(--dp-space-1) 0;
  font-size: var(--dp-font-size-sm);
  font-weight: 600;
  border-block: 1px solid var(--dp-border-faint);
  margin: var(--dp-space-half) 0;
}
.market-panel__book {
  flex: none;
}
.market-panel__tape {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--dp-border-faint);
  padding-top: var(--dp-space-1);
}
.market-panel__trades {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
