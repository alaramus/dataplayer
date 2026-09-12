<script setup lang="ts">
import { computed } from "vue"

import AppTooltip from "./AppTooltip.vue"

export interface SelectOption {
  label: string
  value: string | number
}

const props = withDefaults(
  defineProps<{
    modelValue: unknown
    options: readonly (string | SelectOption)[]
    label?: string
    /**
     * The message, not a boolean: an empty string means no error.
     *
     * Unlike the other fields of the kit this one is not also announced as
     * invalid. QSelect writes the combobox's attributes itself and merges the
     * caller's into it only when it renders a text input, which this never
     * asks for; anything bound here lands on the wrapper around the combobox,
     * where no screen reader reads it. An attribute that goes nowhere is
     * worse than its absence, because a test would then say it is there.
     */
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
     * What several of these are called, for the line that says how many are
     * chosen: "4 schemas selected". Without it the count stands alone, which
     * is all a field can honestly say about values it does not name.
     */
    summaryNoun?: string
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
    summaryNoun: undefined,
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

function labelOf(value: unknown): string {
  for (const option of props.options) {
    if (typeof option === "object") {
      if (option.value === value) return option.label
    } else if (option === value) return option
  }
  return String(value)
}

/** What is ticked, in the words the field would have drawn on its chips. */
const chosen = computed(() =>
  Array.isArray(props.modelValue) ? props.modelValue.map(labelOf) : []
)

/**
 * What a field in a toolbar says it holds: the one choice, or how many.
 *
 * Chips wrap, and a toolbar is one line. Seven schemas ticked in the catalog
 * grew the field into four rows of chips that pushed out of the panel and over
 * the tabs above it. The menu is where the whole list is, and it says which
 * ones are on; this line only has to say how much is.
 *
 * A count and not a name with a count after it: "public +3" reads as a fact
 * about `public` — that it is somehow first, or the one being looked at — and
 * it is not one. Which schema happens to lead the list is an accident of the
 * order they were ticked in.
 */
const summary = computed(() => {
  const [first, ...rest] = chosen.value
  if (first === undefined) return undefined
  if (rest.length === 0) return first
  const noun = props.summaryNoun?.trim().toLowerCase()
  const count = String(chosen.value.length)
  return noun ? `${count} ${noun} selected` : `${count} selected`
})
</script>

<template>
  <q-select
    class="app-select"
    :class="{ 'app-select--compact': compact }"
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
    <!-- One line for several choices, where the field stands in a toolbar.
         See `summary` above. -->
    <template
      v-if="compact && multiple"
      #selected
    >
      <span
        v-if="summary !== undefined"
        class="app-select__summary"
      >
        {{ summary }}
        <AppTooltip v-if="chosen.length > 1">{{ chosen.join(", ") }}</AppTooltip>
      </span>
    </template>

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
/* The one line a toolbar field is: whatever it was given to say, it says it
   in the room the bar has, cut off rather than taken out of. */
.app-select__summary {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-select--compact :deep(.q-field__native) {
  flex-wrap: nowrap;
  overflow: hidden;
}
.app-select :deep(.q-field__append) {
  /* The dropdown arrow rotates on opening. Its intermediate transformed box
     is wider than the icon and can give a scrollable toolbar a scrollbar.
     Keep that paint inside the append area; the popup is teleported outside. */
  overflow: hidden;
}
</style>
