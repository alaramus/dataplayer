<script setup lang="ts">
import AppIconButton from "./AppIconButton.vue"
import AppInput from "./AppInput.vue"
import { appIcons } from "./icons"

/**
 * An instant written as the server reads it, `2026-01-15T00:00:00Z`, typed or
 * picked from a calendar and a clock.
 *
 * The text stays the value: a calendar is a faster way to write it, not a
 * second state to keep in step, and anything the picker cannot express —
 * another offset, seconds — can still be typed. The picker works in UTC,
 * which is what the trailing `Z` says, so a picked day is the same day on
 * every screen.
 */
const props = withDefaults(
  defineProps<{
    modelValue: string
    label?: string
    hint?: string
    placeholder?: string
    error?: string
    disable?: boolean
  }>(),
  { label: undefined, hint: undefined, placeholder: undefined, error: "", disable: false }
)

const emit = defineEmits<{ "update:modelValue": [value: string] }>()

/** Quasar's mask: literal text in brackets, so the `Z` is written, not parsed. */
const MASK = "YYYY-MM-DDTHH:mm:ss[Z]"

function pick(value: unknown) {
  if (typeof value === "string" && value !== props.modelValue) emit("update:modelValue", value)
}
</script>

<template>
  <AppInput
    :model-value="modelValue"
    :label="label"
    :hint="hint"
    :placeholder="placeholder"
    :error="error"
    :disable="disable"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #after>
      <AppIconButton
        :icon="appIcons.calendar"
        tooltip="Pick a day and time, in UTC"
        :disable="disable"
        data-testid="date-time-picker"
      >
        <q-popup-proxy
          cover
          transition-show="scale"
          transition-hide="scale"
        >
          <div class="app-date-time__picker">
            <!-- The application's primary action colour, not Quasar's blue (D131). -->
            <q-date
              :model-value="modelValue"
              :mask="MASK"
              color="dp-action-primary"
              text-color="dp-on-action-primary"
              flat
              minimal
              @update:model-value="pick"
            />
            <q-time
              :model-value="modelValue"
              :mask="MASK"
              color="dp-action-primary"
              text-color="dp-on-action-primary"
              flat
              format24h
              @update:model-value="pick"
            />
          </div>
        </q-popup-proxy>
      </AppIconButton>
    </template>
  </AppInput>
</template>

<style scoped>
.app-date-time__picker {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2);
  background: var(--dp-surface-raised);
}
</style>
