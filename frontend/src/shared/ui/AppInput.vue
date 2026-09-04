<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue: string
    label?: string
    /** `textarea` is a box of several lines rather than a longer line. */
    type?: "text" | "password" | "email" | "textarea"
    /** The message, not a boolean: an empty string means no error. */
    error?: string
    /**
     * The line under the field, in the source's own words: what to write, or
     * what leaving it empty means. Not an error and not a placeholder — it is
     * there whether or not the field is filled.
     */
    hint?: string
    placeholder?: string
    disable?: boolean
    /**
     * A field in a toolbar rather than in a form: tighter, no underline, and
     * no room kept below for a message. Quasar reserves that room whether or
     * not there is anything to put in it, which made a one-line bar 20px
     * taller than the line it holds. An error still colours the field; only
     * its wording has nowhere to go, so a compact field is for a toolbar
     * where nothing is validated.
     */
    compact?: boolean
    /** Offer a cross that empties the field. A search is the reason it exists:
        a query with no way back is a query the user has to erase by hand. */
    clearable?: boolean

  }>(),
  {
    label: undefined,
    type: "text",
    error: "",
    hint: undefined,
    placeholder: undefined,
    disable: false,
    compact: false,
    clearable: false,
  }
)

const emit = defineEmits<{
  "update:modelValue": [value: string]
  /** The field was entered. A caller that shows a stand-in for a value it
      does not have needs to know the moment the user means to type. */
  focus: []
  /** And left, which is when a stand-in nobody replaced comes back. */
  blur: []
}>()

// QInput reports string | number | null whatever its type is. A text field
// deals in strings, so the caller is not made to widen its own state to match
// a detail of the library. Numbers have their own component.
function report(value: string | number | null) {
  emit("update:modelValue", value === null ? "" : String(value))
}
</script>

<template>
  <!-- A field with an example keeps its label above the box: Quasar hides a
         placeholder until the label floats, and a floating label is exactly
         what sits where the example would be. -->
  <q-input
    :model-value="modelValue"
    :label="label"
    :type="type"
    :hint="hint"
    :placeholder="placeholder"
    :stack-label="Boolean(placeholder)"
    :dense="compact"
    :borderless="compact"
    :hide-bottom-space="compact"
    :disable="disable"
    :clearable="clearable"
    :error="Boolean(error)"
    :error-message="error"
    @update:model-value="report"
    @focus="emit('focus')"
    @blur="emit('blur')"
  >
    <!-- Popups belong to the whole field, not to its trailing action area. -->
    <slot />
    <!-- Forwarded rather than left to fall through: a slot does not fall
         through at all, so a search field had no way to carry its magnifier
         except by going around the kit. -->
    <template
      v-if="$slots.prepend"
      #prepend
    >
      <slot name="prepend" />
    </template>
    <!-- A button that belongs beside a field must live in QField's marginal
         area. It is centred against the 56px control there, while the 20px
         message area stays underneath; a flex row around the whole field
         otherwise puts the button one message line too low. -->
    <template
      v-if="$slots.after"
      #after
    >
      <slot name="after" />
    </template>
  </q-input>
</template>
