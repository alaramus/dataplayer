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
 * takes the label column, like a field's. Without one the group spans the
 * form — a column holding nothing reads as a gap — and is named by the
 * `aria-label` it is given instead.
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
    :class="{ 'app-radio-group--form': formLayout && label }"
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
/* Drawn as AppCheckbox draws its box: the size of an icon in a line of text,
   a hairline edge, and the edge darkening under the pointer in place of
   Quasar's halo. Quasar draws the ring as a filled path two units thick, so
   here the edge is a border and that path is left out. */
.app-radio-group__option :deep(.q-radio__inner) {
  width: var(--dp-icon-sm);
  min-width: var(--dp-icon-sm);
  height: var(--dp-icon-sm);
  /* Centred on the name's 20px line rather than hung from its top. */
  margin-top: var(--dp-space-half);
  color: var(--dp-text-muted);
}
.app-radio-group__option :deep(.q-radio__inner--truthy) {
  color: var(--dp-accent);
}
.app-radio-group__option:not(.disabled):hover :deep(.q-radio__inner) {
  color: var(--dp-text);
}
.app-radio-group__option:not(.disabled):hover :deep(.q-radio__inner--truthy) {
  color: var(--dp-accent);
}
.app-radio-group__option :deep(.q-radio__bg) {
  top: 1px;
  left: 1px;
  width: calc(100% - 2px);
  height: calc(100% - 2px);
  box-sizing: border-box;
  border: 1px solid currentColor;
  border-radius: 50%;
}
.app-radio-group__option :deep(.q-radio__bg path) {
  display: none;
}
/* Keep the chosen state visible without Quasar's thick, filled SVG ring. */
.app-radio-group__option :deep(.q-radio__inner--truthy .q-radio__bg) {
  background: radial-gradient(circle, currentColor 0 3px, transparent 3.5px);
}
/* As long as Quasar's own selector, or it wins (AppCheckbox has the trap). */
body.desktop .app-radio-group__option:not(.disabled) :deep(.q-radio__inner)::before {
  content: none;
}
.app-radio-group__option:focus-visible :deep(.q-radio__bg) {
  outline: 2px solid var(--dp-focus-border);
  outline-offset: var(--dp-space-half);
}
.app-radio-group__option :deep(.q-radio__label) {
  padding-left: var(--dp-space-2);
}
.app-radio-group__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.app-radio-group__description {
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
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
.app-form--labels-above .app-radio-group--form,
.app-form--grid .app-radio-group--form {
  display: flex;
}
@container app-form (max-width: 480px) {
  .app-radio-group--form {
    display: flex;
  }
}
</style>
