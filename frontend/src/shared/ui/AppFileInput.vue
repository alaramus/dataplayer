<script setup lang="ts" generic="Value extends File | File[] | null">
import { inject } from "vue"

import { formLayoutKey } from "./formLayout"
import { fieldLook } from "./tokens"

const formLayout = inject(formLayoutKey, false)

const props = defineProps<{
  modelValue: Value
  label?: string
  accept?: string
  /** Whether the field takes a set at once. Its value is then a list. */
  multiple?: boolean
  /** Whether a further choice adds to the set rather than replacing it. */
  append?: boolean
  /**
   * Whether the screen lists what was chosen itself, below the field. The
   * field then only picks: it stays empty rather than repeating the list in
   * one line of names, and a choice still adds to or replaces the set.
   */
  listed?: boolean
}>()

const emit = defineEmits<{ "update:modelValue": [value: Value] }>()

/**
 * What the picker gave back, in the shape this field was asked for.
 *
 * The value of a file field follows `multiple`, and no type states that: a set
 * the user clears comes back as null, while a caller holding a list must still
 * be given a list. So the answer is a list whenever the field offers a set or
 * was given one, and the one assertion below says that and nothing more.
 */
function chosen(value: File | readonly File[] | null) {
  if (props.listed === true) {
    // The field holds nothing, so what it hands over is only what was just
    // picked; adding it to the set is done here, where the set is known.
    const picked = value === null ? [] : value instanceof File ? [value] : [...value]
    const held = Array.isArray(props.modelValue) ? props.modelValue : []
    emit("update:modelValue", (props.append === true ? [...held, ...picked] : picked) as Value)
    return
  }
  if (props.multiple !== true && !Array.isArray(props.modelValue)) {
    emit("update:modelValue", value as Value)
    return
  }
  const many = value === null ? [] : value instanceof File ? [value] : [...value]
  emit("update:modelValue", many as Value)
}
</script>

<template>
  <q-file
    :class="{ 'app-form-field': formLayout }"
    v-bind="fieldLook(formLayout)"
    :model-value="listed ? null : modelValue"
    :label="label"
    :aria-label="$attrs['aria-label'] ?? label"
    :accept="accept"
    :multiple="multiple"
    :append="listed ? false : append"
    @update:model-value="chosen"
  >
    <template
      v-if="formLayout && label"
      #before
    >
      <span>{{ label }}</span>
    </template>
    <template
      v-if="$slots.after"
      #after
    >
      <slot name="after" />
    </template>
  </q-file>
</template>
