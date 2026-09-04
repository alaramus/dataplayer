<script setup lang="ts">
import { computed } from "vue"

export interface SelectOption {
  label: string
  value: string | number
}

const props = withDefaults(
  defineProps<{
    modelValue: unknown
    options: readonly (string | SelectOption)[]
    label?: string
    error?: string
    /**
     * The line under the field, in the source's own words: what to write, or
     * what leaving it empty means. Not an error and not a placeholder — it is
     * there whether or not the field is filled.
     */
    hint?: string
    loading?: boolean
    disable?: boolean
    /** Several at once, reported as an array. */
    multiple?: boolean
    /**
     * A field in a toolbar rather than in a form: tighter, no underline, and
     * no room kept below for a message. Quasar reserves that room whether or
     * not there is anything to put in it, which made a one-line bar 20px
     * taller than the line it holds. An error still colours the field; only
     * its wording has nowhere to go, so a compact field is for a toolbar
     * where nothing is validated.
     */
    compact?: boolean
  }>(),
  {
    label: undefined,
    error: "",
    hint: undefined,
    loading: false,
    disable: false,
    multiple: false,
    compact: false,
  }
)

const emit = defineEmits<{ "update:modelValue": [value: unknown] }>()

// A caller passes either plain strings or {label, value} pairs, and the four
// Quasar props that distinguish them are derived here rather than repeated at
// every call site.
const labelled = computed(() => props.options.some((option) => typeof option === "object"))
</script>

<template>
  <q-select
    class="app-select"
    :model-value="modelValue"
    :options="options"
    :label="label"
    :hint="hint"
    :option-value="labelled ? 'value' : undefined"
    :option-label="labelled ? 'label' : undefined"
    :emit-value="labelled"
    :map-options="labelled"
    :loading="loading"
    :multiple="multiple"
    :use-chips="multiple"
    :dense="compact"
    :borderless="compact"
    :hide-bottom-space="compact"
    :disable="disable"
    :error="Boolean(error)"
    :error-message="error"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <!-- Keep companion actions in the field's 56px marginal area, above the
         separately reserved error-message line. AppInput exposes the same
         contract, so screens never compensate for QField geometry themselves. -->
    <template
      v-if="$slots.after"
      #after
    >
      <slot name="after" />
    </template>
  </q-select>
</template>

<style scoped>
.app-select :deep(.q-field__append) {
  /* The dropdown arrow rotates on opening. Its intermediate transformed box
     is wider than the icon and can give a scrollable toolbar a scrollbar.
     Keep that paint inside the append area; the popup is teleported outside. */
  overflow: hidden;
}
</style>
