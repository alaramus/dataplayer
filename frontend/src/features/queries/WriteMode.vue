<script setup lang="ts">
import { computed, ref } from "vue"

import type { UnlockState } from "@/client"
import { AppButton, AppInput, AppSelect } from "@/shared/ui"

/**
 * Choosing what this console may do, and leaving read-only on purpose (D66).
 *
 * Every document opens read-only and this is the only way out. The name of the
 * connection is typed here and checked on the server, which is where it counts.
 * Nothing is remembered: a reload opens read-only again.
 *
 * Which modes exist is the source's answer — a source that only reads (D77)
 * offers one, and one option is not a choice, so nothing is drawn.
 */

type Mode = "read" | "auto_commit" | "manual"

const props = defineProps<{
  mode: Mode
  /** What the source said it accepts, in the profile it published. */
  modes: Mode[]
  unlock: UnlockState | undefined
  connectorLabel: string | null
  busy: boolean
}>()
const emit = defineEmits<{
  "update:mode": [mode: "read" | "auto_commit" | "manual"]
  unlock: [typedName: string]
  relock: []
}>()

const typed = ref("")

const policy = computed(() => props.unlock?.policy ?? "confirm_writes")
const unlocked = computed(() => props.unlock?.unlocked === true)
const forbidden = computed(() => policy.value === "read_only" || !writable.value)
const writable = computed(
  () => props.unlock !== undefined && props.unlock.access !== "read"
)
const LABELS: Record<Mode, string> = {
  read: "Read only",
  auto_commit: "Auto-commit",
  manual: "Transaction",
}
const options = computed(() =>
  props.modes.map((value) => ({ label: LABELS[value], value }))
)
/** Whether there is anything here to decide. */
const choosable = computed(() => props.modes.length > 1)

/**
 * Whether the question is on screen: a writing mode, chosen while writes are
 * locked and while the connection admits them at all.
 *
 * Read from all three, and not set when the mode changes. What the connection
 * allows can change under an open console — its owner may close writing on it
 * or open it again — and a flag written on the way in kept asking, or kept not
 * asking, whatever the connection said afterwards (D66).
 */
const asking = computed(
  () => props.mode !== "read" && !unlocked.value && !forbidden.value
)

function choose(value: unknown) {
  if (value !== "read" && value !== "auto_commit" && value !== "manual") return
  emit("update:mode", value)
}
</script>

<template>
  <div
    v-if="choosable"
    class="write-mode"
  >
    <AppSelect
      :model-value="mode"
      :options="options"
      :disable="forbidden && mode === 'read'"
      compact
      class="write-mode__select"
      data-testid="query-mode"
      @update:model-value="choose"
    />
    <span
      v-if="forbidden"
      class="write-mode__note"
      data-testid="query-write-forbidden"
    >{{ unlock?.reason ?? "This connection is read only" }}</span>
    <AppButton
      v-else-if="unlocked"
      variant="quiet"
      size="sm"
      label="Lock writing"
      data-testid="query-relock"
      @click="emit('relock')"
    />

    <div
      v-if="asking"
      class="write-mode__ask"
      data-testid="query-unlock"
    >
      <template v-if="policy === 'confirm_writes'">
        <span class="write-mode__note">
          Type <strong>{{ connectorLabel }}</strong> to write through it
        </span>
        <AppInput
          v-model="typed"
          placeholder="Name of the connection"
          compact
          class="write-mode__typed"
          data-testid="query-unlock-name"
        />
      </template>
      <span
        v-else
        class="write-mode__note"
      >
        Statements in this console will change {{ connectorLabel }}
      </span>
      <AppButton
        variant="primary"
        size="sm"
        label="Allow writing"
        :disable="busy || (policy === 'confirm_writes' && typed.trim() === '')"
        data-testid="query-unlock-submit"
        @click="emit('unlock', typed)"
      />
      <AppButton
        variant="quiet"
        size="sm"
        label="Stay reading"
        data-testid="query-unlock-cancel"
        @click="emit('update:mode', 'read')"
      />
    </div>
  </div>
</template>

<style scoped>
.write-mode {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.write-mode__select {
  flex: none;
  min-width: 130px;
}
.write-mode__ask {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border: 1px solid var(--dp-border-faint);
  border-radius: 4px;
  background: var(--dp-chrome-raised);
}
.write-mode__typed {
  flex: 0 1 220px;
}
.write-mode__note {
  color: var(--dp-text-muted);
  font-size: 11px;
}
</style>
