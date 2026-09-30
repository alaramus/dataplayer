<script setup lang="ts">
import { computed, inject, useTemplateRef } from "vue"

import { formLayoutKey } from "./formLayout"
import { fieldLook } from "./tokens"

import type { QSelect } from "quasar"

import AppTooltip from "./AppTooltip.vue"
import AppIconButton from "./AppIconButton.vue"

const formLayout = inject(formLayoutKey, false)

export interface SelectOption {
  label: string
  value: string | number
  /** A non-selectable heading separating related choices. */
  group?: boolean
  /** A visible choice that cannot be selected yet. */
  disable?: boolean
  /** A quiet second line explaining a choice. */
  description?: string
  /** Meaning shown before the choice. */
  icon?: string
  /** An action belonging to this choice rather than selecting it. */
  actionIcon?: string
  actionLabel?: string
  actionActive?: boolean
  /**
   * A state the choice is in, drawn after its name in the field once it is
   * chosen: the list says it in the description, and the field shows only
   * the name. The icon is a mark, not a command; the description is its
   * tooltip.
   */
  stateIcon?: string
  stateActive?: boolean
  /**
   * A choice out of the ordinary, in the caution colour: in the list, and in
   * the field while it is the one chosen.
   */
  tone?: "warning"
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
     * chosen: "4 schemas". Without it the count stands alone as "4 selected",
     * which is all a field can honestly say about values it does not name.
     */
    summaryNoun?: string
    /**
     * A field in a toolbar rather than in a form: tighter, no underline, and
     * no room kept below for a message. Quasar reserves that room whether or
     * not there is anything to put in it, which made a one-line bar 20px
     * taller than the line it holds. An error reserves its message space
     * until corrected, including in a compact toolbar.
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

const emit = defineEmits<{
  "update:modelValue": [value: unknown]
  "optionAction": [option: SelectOption]
}>()

const field = useTemplateRef<QSelect>("field")

// The click never reaches the field's own handler, so the popup would stay
// open over whatever the action shows — a key window, here. The action takes
// over the interaction, and the menu it came from goes away.
function act(option: SelectOption) {
  field.value?.hidePopup()
  emit("optionAction", option)
}

// A caller passes either plain strings or {label, value} pairs, and the four
// Quasar props that distinguish them are derived here rather than repeated at
// every call site.
const labelled = computed(() => props.options.some((option) => typeof option === "object"))
/** A toolbar field says its name beside it, never floated over its value. */
const inlineLabel = computed(() => props.compact && !formLayout)

function labelOf(value: unknown): string {
  for (const option of props.options) {
    if (typeof option === "object") {
      if (option.value === value) return option.label
    } else if (option === value) return option
  }
  return String(value)
}

/** The one option a single field holds, when it is one of the labelled ones. */
const single = computed(() =>
  props.multiple
    ? undefined
    : props.options.find(
      (option): option is SelectOption => typeof option === "object" && option.value === props.modelValue
    )
)

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
  return noun ? `${count} ${noun}` : `${count} selected`
})
</script>

<template>
  <q-select
    ref="field"
    class="app-select"
    :class="{ 'app-select--compact': compact, 'app-select--inline': inlineLabel, 'app-form-field': formLayout }"
    :model-value="modelValue"
    :options="options"
    :label="label"
    :aria-label="formLayout ? label : undefined"
    :hint="hint"
    :option-value="labelled ? 'value' : undefined"
    :option-label="labelled ? 'label' : undefined"
    :option-disable="labelled ? (option: SelectOption) => Boolean(option.group || option.disable) : undefined"
    :emit-value="labelled"
    :map-options="labelled"
    :loading="loading"
    :multiple="multiple"
    :use-chips="multiple"
    v-bind="{ ...fieldLook(formLayout, compact, Boolean(error)), color: 'dp-field-focus' }"
    :disable="disable"
    :error="Boolean(error)"
    :error-message="error"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template
      v-if="(formLayout || inlineLabel) && label"
      #before
    >
      <!-- Hidden from a reader beside a toolbar field: its name is Quasar's
           own label, kept out of sight, and saying it twice named the field
           "Column Column". -->
      <span
        :class="{ 'app-select__inline-label': inlineLabel }"
        :aria-hidden="inlineLabel ? 'true' : undefined"
      >{{ label }}</span>
    </template>
    <template
      v-if="labelled && options.some((option) => typeof option === 'object' && (option.group || option.description || option.icon || option.actionIcon || option.tone))"
      #option="scope"
    >
      <q-item
        v-if="scope.opt.group"
        v-bind="scope.itemProps"
      >
        <q-item-section>
          <q-item-label header>
            {{ scope.opt.label }}
          </q-item-label>
        </q-item-section>
      </q-item>
      <q-item
        v-else
        v-bind="scope.itemProps"
        :class="{ 'app-select__option--warning': scope.opt.tone === 'warning' }"
      >
        <q-item-section
          v-if="scope.opt.icon"
          avatar
        >
          <q-icon
            :name="scope.opt.icon"
            :color="scope.opt.actionActive ? 'positive' : undefined"
          />
        </q-item-section>
        <q-item-section>
          <q-item-label>{{ scope.opt.label }}</q-item-label>
          <q-item-label
            v-if="scope.opt.description"
            caption
          >
            {{ scope.opt.description }}
          </q-item-label>
        </q-item-section>
        <q-item-section
          v-if="scope.opt.actionIcon && scope.opt.actionLabel"
          side
        >
          <AppIconButton
            :icon="scope.opt.actionIcon"
            :tooltip="scope.opt.actionLabel"
            :active="scope.opt.actionActive"
            @click.stop.prevent="act(scope.opt)"
          />
        </q-item-section>
      </q-item>
    </template>
    <!-- One line for several choices, where the field stands in a toolbar.
         See `summary` above.
         Trap: a key on the root of either #selected. Without one, a slot that
         appears after the options load patches the <span> QSelect drew
         before it, and Vue sets this component's scope attribute only on a
         new element: the styles below then miss it, the gap by the key
         included, on some openings and not others. -->
    <template
      v-if="compact && multiple"
      #selected
    >
      <span
        v-if="summary !== undefined"
        key="summary"
        class="app-select__summary"
      >
        {{ summary }}
        <AppTooltip v-if="chosen.length > 1">{{ chosen.join(", ") }}</AppTooltip>
      </span>
    </template>
    <template
      v-else-if="single?.stateIcon || single?.tone"
      #selected
    >
      <span
        key="chosen"
        class="app-select__chosen"
        :class="{ 'app-select__chosen--warning': single.tone === 'warning' }"
      >
        <span class="app-select__chosen-label">{{ single.label }}</span>
        <q-icon
          v-if="single.stateIcon"
          :name="single.stateIcon"
          class="app-select__state"
          :class="{ 'app-select__state--on': single.stateActive }"
          size="var(--dp-icon-sm)"
        >
          <AppTooltip v-if="single.description">{{ single.description }}</AppTooltip>
        </q-icon>
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
.app-select__chosen {
  display: inline-flex;
  align-items: center;
  gap: var(--dp-space-1);
  min-width: 0;
}
.app-select__chosen--warning,
.app-select__option--warning { color: var(--dp-tone-warning-text); }
.app-select__chosen-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-select__state { flex: none; color: var(--dp-text-muted); }
.app-select__state--on { color: var(--dp-content-success); }
/* A toolbar field is a control of the toolbar's height, and its name stands
   beside it rather than floating over its value: a floated label and a value
   need 40px, and "Per page" sat its 100 below the line of the range beside
   it. The height is whatever holds it says (--dp-field-height). Trap: a
   select is "auto-height" to Quasar, which keeps its control 40px tall three
   classes deep; under :where() this counted none of them and lost. */
.app-select--compact.q-field--dense :deep(.q-field__control),
.app-select--compact.q-field--dense :deep(.q-field__marginal) {
  height: var(--dp-field-height);
  min-height: var(--dp-field-height);
}
.app-select--compact.q-field--dense :deep(.q-field__native) {
  min-height: var(--dp-field-height);
  padding-top: 0;
  padding-bottom: 0;
}
/* Quasar's label stays for the field's name and is kept out of sight, as a
   form's is (AppForm); the name shown is the one beside the field. */
.app-select--inline :deep(.q-field__label) {
  display: none;
}
/* Quasar adds a top inset for dense, labelled, auto-height selects. Match
   those state classes so this reset still wins when production CSS is loaded
   after the component stylesheet. */
.app-select.app-select--inline.q-field--auto-height.q-field--labeled :deep(.q-field__control-container) {
  padding-top: 0;
  padding-bottom: 0;
}
.app-select.app-select--inline.q-field--auto-height.q-field--labeled :deep(.q-field__native) {
  min-height: var(--dp-field-height);
  padding-top: 0;
  padding-bottom: 0;
}
.app-select__inline-label {
  padding-right: var(--dp-space-2);
  font-size: var(--dp-font-size);
  color: var(--dp-text-muted);
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
