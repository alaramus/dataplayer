<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"

import type { TransactionPublic } from "@/client"
import { AppBanner, AppButton } from "@/shared/ui"

/**
 * What an open transaction has done, and the two ways it ends (D66).
 *
 * Also the commit preview: what is listed here — the connection, how long it
 * has been open, what it changed and where — is what the server would list,
 * because it is the same answer. A screen that summarised it a second way
 * could disagree with the first.
 *
 * The countdown is the promise the lease makes: five minutes idle and the
 * server rolls this back, so the last minute is said out loud rather than
 * happening quietly.
 */

const props = defineProps<{ transaction: TransactionPublic; busy: boolean }>()
const emit = defineEmits<{ commit: []; rollback: [] }>()

const now = ref(Date.now())
let ticking: ReturnType<typeof setInterval> | null = null

// Optional in the schema because a transaction may answer before it has done
// anything; empty is the honest reading of that.
const state = computed(() => props.transaction.state)
const targets = computed(() => state.value.targets ?? [])
// Counted separately in the preview, because committing a structure change is
// a different sort of decision from committing rows (D66).
const structural = computed(() => state.value.ddl_statements ?? 0)
const remaining = computed(() =>
  Math.max(0, new Date(props.transaction.expires_at).getTime() - now.value)
)
const closing = computed(() => remaining.value < 60_000)
const countdown = computed(() => {
  const seconds = Math.ceil(remaining.value / 1000)
  return seconds >= 60
    ? `${Math.floor(seconds / 60)}m ${seconds % 60}s`
    : `${seconds}s`
})
const age = computed(() => {
  const seconds = Math.floor(props.transaction.age_seconds)
  return seconds >= 60 ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : `${seconds}s`
})

onMounted(() => {
  ticking = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})
onBeforeUnmount(() => {
  if (ticking !== null) clearInterval(ticking)
})
</script>

<template>
  <AppBanner
    :tone="state.broken ? 'error' : closing ? 'warning' : 'info'"
    class="transaction"
    data-testid="transaction-bar"
  >
    <div class="transaction__row">
      <span class="transaction__what">
        <template v-if="state.broken">
          This transaction failed and can only be rolled back.
        </template>
        <template v-else>
          Open on {{ transaction.connector_label }} for {{ age }} ·
          {{ state.mutating_statements }} changing
          {{ state.mutating_statements === 1 ? "statement" : "statements" }} ·
          {{ state.affected_rows }} rows
          <template v-if="structural > 0">
            · {{ structural }} changing the structure
          </template>
          <template v-if="targets.length > 0">
            · {{ targets.join(", ") }}
          </template>
        </template>
      </span>
      <span
        class="transaction__countdown"
        :data-closing="closing"
        data-testid="transaction-countdown"
      >Rolls back in {{ countdown }}</span>
      <AppButton
        variant="primary"
        size="sm"
        label="Commit"
        :disable="busy || state.broken"
        data-testid="transaction-commit"
        @click="emit('commit')"
      />
      <AppButton
        variant="secondary"
        size="sm"
        label="Roll back"
        :disable="busy"
        data-testid="transaction-rollback"
        @click="emit('rollback')"
      />
    </div>
  </AppBanner>
</template>

<style scoped>
.transaction {
  flex: none;
}
.transaction__row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.transaction__what {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.transaction__countdown {
  flex: none;
  font-size: 11px;
  color: var(--dp-text-muted);
}
.transaction__countdown[data-closing="true"] {
  color: var(--dp-callout-caution);
  font-weight: 600;
}
</style>
