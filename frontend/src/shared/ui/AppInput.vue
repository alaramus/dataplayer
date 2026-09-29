<script setup lang="ts">
import { computed, inject, useAttrs, useId } from "vue"

import { formLayoutKey } from "./formLayout"
import { fieldLook } from "./tokens"

const formLayout = inject(formLayoutKey, false)

defineOptions({ inheritAttrs: false })

const errorId = `${useId()}-error`
const attrs = useAttrs()

const props = withDefaults(
  defineProps<{
    modelValue: string
    label?: string
    /** Keep the label clear of values supplied by browser autofill. */
    persistentLabel?: boolean
    /**
     * `textarea` is a box of several lines rather than a longer line; `time`
     * is a time of day, "09:30", picked with the browser's own control.
     */
    type?: "text" | "password" | "email" | "textarea" | "time"
    /**
     * The message, not a boolean: an empty string means no error.
     *
     * A field carrying one also says so to a screen reader. Quasar colours it
     * and prints the message and stops there — `aria-invalid` appears nowhere
     * in the library — so the kit binds it, once, for every field.
     */
    error?: string
    /**
     * The line under the field, in the source's own words: what to write, or
     * what leaving it empty means. Not an error and not a placeholder — it is
     * there whether or not the field is filled.
     */
    hint?: string
    /**
     * An example inside the empty box, gone the moment anything is typed.
     *
     * A field carrying one keeps its label above the box whether or not it was
     * asked to: Quasar hides a placeholder until the label floats, and a
     * floating label sits exactly where the example would be.
     */
    placeholder?: string
    disable?: boolean
    /**
     * A field in a toolbar rather than in a form: tighter, no underline, and
     * no room kept below for a message. Quasar reserves that room whether or
     * not there is anything to put in it, which made a one-line bar 20px
     * taller than the line it holds. An error reserves its message space
     * until corrected, including in a compact toolbar.
     */
    compact?: boolean
    /** Offer a cross that empties the field. A search is the reason it exists:
        a query with no way back is a query the user has to erase by hand. */
    clearable?: boolean
    prependIcon?: string
    /**
     * A `textarea` that follows what is typed instead of standing at a fixed
     * number of rows, and without the corner grip a plain one carries.
     *
     * It grows without end, so a caller puts it somewhere with a ceiling: a
     * `max-height` on the field's own textarea, or a box that bounds it.
     */
    grow?: boolean
    /** A value read character by character: an address, a generated password. */
    monospace?: boolean
  }>(),
  {
    label: undefined,
    persistentLabel: false,
    type: "text",
    error: "",
    hint: undefined,
    placeholder: undefined,
    disable: false,
    compact: false,
    clearable: false,
    prependIcon: undefined,
    grow: false,
    monospace: false,
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

/**
 * A field in a toolbar rather than a form: its name is the placeholder, not a
 * label floated over the value, so it stands at the toolbar's height.
 */
const toolbar = computed(() => props.compact && !formLayout)

// QInput reports string | number | null whatever its type is. A text field
// deals in strings, so the caller is not made to widen its own state to match
// a detail of the library. Numbers have their own component.
function report(value: string | number | null) {
  emit("update:modelValue", value === null ? "" : String(value))
}
</script>

<template>
  <q-input
    :class="{ 'app-form-field': formLayout, 'app-input--monospace': monospace, 'app-input--compact': toolbar }"
    v-bind="{ ...attrs, ...fieldLook(formLayout, compact, Boolean(error)) }"
    :model-value="modelValue"
    :label="formLayout || toolbar ? undefined : label"
    :aria-label="attrs['aria-label'] ?? (formLayout || toolbar ? label : undefined)"
    :type="type"
    :hint="hint"
    :placeholder="placeholder ?? (toolbar ? label : undefined)"
    :stack-label="persistentLabel || Boolean(placeholder)"
    :autogrow="grow"
    :disable="disable"
    :clearable="clearable"
    :error="Boolean(error)"
    :aria-invalid="error ? 'true' : undefined"
    :aria-describedby="
      [attrs['aria-describedby'], error ? errorId : undefined].filter(Boolean).join(' ') || undefined
    "
    @update:model-value="report"
    @focus="emit('focus')"
    @blur="emit('blur')"
  >
    <template
      v-if="formLayout && label"
      #before
    >
      <span>{{ label }}</span>
    </template>
    <template #error>
      <span
        :id="errorId"
        role="alert"
      >{{ error }}</span>
    </template>
    <!-- Popups belong to the whole field, not to its trailing action area. -->
    <slot />
    <!-- Forwarded rather than left to fall through: a slot does not fall
         through at all, so a search field had no way to carry its magnifier
         except by going around the kit. -->
    <template
      v-if="$slots.prepend || prependIcon"
      #prepend
    >
      <slot name="prepend">
        <q-icon :name="prependIcon" />
      </slot>
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

<style scoped>
.app-input--monospace :deep(.q-field__native) {
  font-family: var(--dp-font-mono);
}
/* A toolbar field is a control of the toolbar's height, whatever holds it
   says that height is (--dp-field-height: a card head's strip). Trap: Quasar
   sets a dense field's control at 40px three classes deep, and the :where()
   this used to sit under counted none of them — every compact field in the
   application stood 40px beside its 32px buttons. */
.app-input--compact.q-field--dense :deep(.q-field__control),
.app-input--compact.q-field--dense :deep(.q-field__marginal) {
  height: var(--dp-field-height);
  min-height: var(--dp-field-height);
}
.app-input--compact.q-field--dense :deep(.q-field__native) {
  min-height: var(--dp-field-height);
  padding-top: 0;
  padding-bottom: 0;
}
</style>
