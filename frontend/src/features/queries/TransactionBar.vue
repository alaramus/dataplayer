<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"

import type { TransactionPublic } from "@/client"
import { t } from "@/shared/i18n"
import { AppBanner, AppButton } from "@/shared/ui"

/**
 * What an open transaction has done, and the two ways it ends (D66).
 *
 * The commit preview lists what the server would list, because it is the same
 * answer: a screen summarising it a second way could disagree. The countdown
 * is the lease — five minutes idle and the server rolls this back, so the last
 * minute is said out loud rather than happening quietly.
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
const changing = computed(() => state.value.mutating_statements ?? 0)
const affected = computed(() => state.value.affected_rows ?? 0)
const remaining = computed(() =>
  Math.max(0, new Date(props.transaction.expires_at).getTime() - now.value)
)
const closing = computed(() => remaining.value < 60_000)
function minutesAndSeconds(seconds: number): string {
  return seconds >= 60
    ? t("queries.duration.minutes_seconds", { m: Math.floor(seconds / 60), s: seconds % 60 })
    : t("queries.duration.seconds", { n: seconds })
}
const countdown = computed(() => minutesAndSeconds(Math.ceil(remaining.value / 1000)))
const age = computed(() => minutesAndSeconds(Math.floor(props.transaction.age_seconds)))

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
          {{ t("queries.transaction.failed") }}
        </template>
        <template v-else>
          {{ t("queries.transaction.open", { connection: transaction.connector_label, age }) }} ·
          {{ t("queries.transaction.changing", { n: changing }, changing) }} ·
          {{ t("queries.transaction.rows", { n: affected }, affected) }}
          <template v-if="structural > 0">
            · {{ t("queries.transaction.structural", { n: structural }) }}
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
      >{{ t("queries.transaction.rolls_back", { time: countdown }) }}</span>
      <!-- A failed transaction can only be rolled back, so Commit is not
           offered at all and Roll back is the one action (D187): a disabled
           Commit beside it read as the thing to press. -->
      <AppButton
        v-if="!state.broken"
        variant="primary"
        size="sm"
        :label="t('queries.transaction.commit')"
        :disable="busy"
        data-testid="transaction-commit"
        @click="emit('commit')"
      />
      <AppButton
        :variant="state.broken ? 'primary' : 'secondary'"
        size="sm"
        :label="t('queries.transaction.roll_back')"
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
  gap: var(--dp-space-2);
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
  font-size: var(--dp-font-size-xs);
  color: var(--dp-text-muted);
}
.transaction__countdown[data-closing="true"] {
  color: var(--dp-tone-warning-text);
  font-weight: 600;
}
</style>
