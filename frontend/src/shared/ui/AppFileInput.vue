<script setup lang="ts" generic="Value extends File | File[] | null">
const props = defineProps<{
  modelValue: Value
  label?: string
  accept?: string
  /** Whether the field takes a set at once. Its value is then a list. */
  multiple?: boolean
  /** Whether a further choice adds to the set rather than replacing it. */
  append?: boolean
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
    :model-value="modelValue"
    :label="label"
    :accept="accept"
    :multiple="multiple"
    :append="append"
    @update:model-value="chosen"
  >
    <template
      v-if="$slots.after"
      #after
    >
      <slot name="after" />
    </template>
  </q-file>
</template>
