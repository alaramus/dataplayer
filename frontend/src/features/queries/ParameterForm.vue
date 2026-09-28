<script setup lang="ts">
import type { ParameterEntry } from "@/features/queries/console"
import { AppCheckbox, AppInput } from "@/shared/ui"

/**
 * What the script asks for before it can run (D62).
 *
 * A value, or SQL null, and two choices about it: whether to remember it here
 * and whether it is a secret — which is the same as saying it will not be
 * remembered anywhere.
 */

const props = defineProps<{ entries: ParameterEntry[] }>()
const emit = defineEmits<{ "update:entries": [entries: ParameterEntry[]] }>()

function change(name: string, patch: Partial<ParameterEntry>) {
  emit(
    "update:entries",
    props.entries.map((entry) =>
      entry.name === name ? { ...entry, ...patch } : entry
    )
  )
}
</script>

<template>
  <div
    class="parameters"
    data-testid="query-parameters"
  >
    <div
      v-for="entry in entries"
      :key="entry.name"
      class="parameters__row"
      :data-testid="`parameter-${entry.name}`"
    >
      <span class="parameters__name">:{{ entry.name }}</span>
      <AppInput
        :model-value="entry.value"
        :type="entry.secret ? 'password' : 'text'"
        :disable="entry.isNull"
        :placeholder="entry.isNull ? 'SQL null' : 'value'"
        compact
        class="parameters__value"
        :data-testid="`parameter-value-${entry.name}`"
        @update:model-value="change(entry.name, { value: $event })"
      />
      <AppCheckbox
        :model-value="entry.isNull"
        label="null"
        dense
        :data-testid="`parameter-null-${entry.name}`"
        @update:model-value="change(entry.name, { isNull: $event === true })"
      />
      <AppCheckbox
        :model-value="entry.secret"
        label="secret"
        dense
        :data-testid="`parameter-secret-${entry.name}`"
        @update:model-value="
          change(entry.name, {
            secret: $event === true,
            // A secret is used and forgotten, so it cannot also be remembered.
            remember: $event === true ? false : entry.remember,
          })
        "
      />
      <AppCheckbox
        :model-value="entry.remember"
        label="remember"
        dense
        :disable="entry.secret"
        :data-testid="`parameter-remember-${entry.name}`"
        @update:model-value="change(entry.name, { remember: $event === true })"
      />
    </div>
  </div>
</template>

<style scoped>
.parameters {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  padding: var(--dp-space-2) var(--dp-space-2);
  border: 1px solid var(--dp-border-faint);
  border-radius: var(--dp-radius-control);
  background: var(--dp-chrome-raised);
}
.parameters__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}
.parameters__name {
  flex: none;
  min-width: 120px;
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-sm);
}
.parameters__value {
  flex: 0 1 260px;
  min-width: 0;
}
</style>
