<script setup lang="ts">
import { inject, useAttrs, useId } from "vue"

import { formLayoutKey } from "./formLayout"
import { radioLook } from "./tokens"

export interface RadioOption {
  label: string
  value: string
  /** What choosing it means, or why it cannot be chosen. Always shown. */
  description?: string
  disable?: boolean
}

/**
 * One of a few choices, each with what it means beside it.
 *
 * Apart from AppSelect on purpose: a select hides its options and their
 * descriptions until opened, which is right for a long list and wrong for two
 * or three that the person is meant to compare. In a form the group's label
 * takes the label column, like a field's.
 */
const props = withDefaults(
  defineProps<{
    modelValue: string
    options: readonly RadioOption[]
    label?: string
  }>(),
  { label: undefined }
)

const emit = defineEmits<{ "update:modelValue": [value: string] }>()

const formLayout = inject(formLayoutKey, false)
const attrs = useAttrs()
const id = useId()

/** An option is found the way the group is: `download-scope` → `download-scope-all`. */
function optionTestId(option: RadioOption): string | undefined {
  const group = attrs["data-testid"]
  return typeof group === "string" ? `${group}-${option.value}` : undefined
}

function choose(value: unknown) {
  if (typeof value === "string" && value !== props.modelValue) emit("update:modelValue", value)
}
</script>

<template>
  <div
    class="app-radio-group"
    :class="{ 'app-radio-group--form': formLayout }"
    role="radiogroup"
    :aria-labelledby="label ? `${id}-label` : undefined"
  >
    <span
      v-if="label"
      :id="`${id}-label`"
      class="app-radio-group__label"
    >{{ label }}</span>
    <div class="app-radio-group__options">
      <q-radio
        v-for="option in options"
        :key="option.value"
        v-bind="radioLook(formLayout)"
        class="app-radio-group__option"
        :model-value="modelValue"
        :val="option.value"
        :disable="option.disable"
        :aria-label="option.label"
        :aria-describedby="option.description ? `${id}-${option.value}` : undefined"
        :data-testid="optionTestId(option)"
        @update:model-value="choose"
      >
        <span class="app-radio-group__text">
          <span>{{ option.label }}</span>
          <span
            v-if="option.description"
            :id="`${id}-${option.value}`"
            class="app-radio-group__description"
          >{{ option.description }}</span>
        </span>
      </q-radio>
    </div>
  </div>
</template>

<style scoped>
.app-radio-group {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
}
.app-radio-group__options {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  min-width: 0;
}
/* The mark stands by the option's name, not halfway down its description. */
.app-radio-group__option {
  align-items: flex-start;
}
.app-radio-group__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.app-radio-group__description {
  font-size: 12px;
  color: var(--dp-text-muted);
}
.app-radio-group--form {
  display: grid;
  grid-template-columns: var(--dp-form-label-width) minmax(0, 1fr);
  /* Tops rather than baselines: QRadio's mark, not its name, sets the
     option's baseline, and the label then sat half a line low. */
  align-items: start;
}
.app-radio-group--form .app-radio-group__label {
  padding-right: var(--dp-space-3);
}
@container app-form (max-width: 480px) {
  .app-radio-group--form {
    display: flex;
  }
}
</style>
