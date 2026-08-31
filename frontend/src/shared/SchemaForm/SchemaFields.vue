<script setup lang="ts">
import { computed, ref, watch } from "vue"

import AppInput from "@/shared/ui/AppInput.vue"
import AppNumberInput from "@/shared/ui/AppNumberInput.vue"
import AppSelect from "@/shared/ui/AppSelect.vue"
import AppToggle from "@/shared/ui/AppToggle.vue"

import { fieldRows } from "./jsonSchema"
import type { FieldSpec } from "./jsonSchema"

const props = defineProps<{
  fields: FieldSpec[]
  modelValue: Record<string, unknown>
  errors: Record<string, string>
  /**
   * The connection being edited already has secrets stored, and the server
   * never sends them back. An untouched secret field therefore stands in for
   * a value it does not hold.
   */
  secretsAreStored?: boolean
  /**
   * Shown but not editable: the connection is somebody else's, and it is read
   * through a grant. Every control is disabled rather than the form hidden,
   * because seeing what one is connected to is part of what a grant gives.
   */
  disable?: boolean
}>()

const emit = defineEmits<{
  "update:modelValue": [value: Record<string, unknown>]
}>()

function update(name: string, value: unknown) {
  emit("update:modelValue", { ...props.modelValue, [name]: value })
}

// Lines rather than a flat column: which fields share one is decided by the
// model that declares them and arrives in the schema.
const rows = computed(() => fieldRows(props.fields))

function textValue(name: string): string {
  const value = props.modelValue[name]
  return value === null || value === undefined ? "" : String(value)
}

function numberValue(name: string): number | null {
  const value = props.modelValue[name]
  return typeof value === "number" ? value : null
}

/**
 * A stored secret, shown as a stand-in until the user means to replace it.
 *
 * The alternative — a placeholder — reads as an empty field, and an empty
 * field beside a saved connection says the password was lost. This says there
 * is one and that it is not being shown; touching it empties the field and
 * whatever is typed then replaces it. A field left untouched reports nothing,
 * and the server keeps what it has.
 */
const HIDDEN = "<hidden>"

const touched = ref<Set<string>>(new Set())

function isHidden(field: FieldSpec): boolean {
  return (
    props.secretsAreStored === true &&
    field.kind === "password" &&
    !touched.value.has(field.name) &&
    (props.modelValue[field.name] ?? "") === ""
  )
}

function reveal(name: string) {
  touched.value = new Set(touched.value).add(name)
}

/**
 * Leaving without typing puts the stand-in back.
 *
 * A field entered and left unchanged has changed nothing, and an empty box is
 * not what is stored there. Only an emptied field goes back: whatever was
 * typed stays, and that is what replaces the stored secret.
 */
function restore(name: string) {
  if ((props.modelValue[name] ?? "") !== "") return
  const remaining = new Set(touched.value)
  remaining.delete(name)
  touched.value = remaining
}

// A different connection in the same window is a different set of secrets.
watch(
  () => props.fields,
  () => {
    touched.value = new Set()
  }
)
</script>

<template>
  <div class="schema-fields">
    <div
      v-for="(row, index) in rows"
      :key="index"
      class="schema-fields__row"
    >
      <template
        v-for="field in row"
        :key="field.name"
      >
        <template v-if="field.kind === 'hidden'" />
        <AppToggle
          v-else-if="field.kind === 'boolean'"
          :data-testid="`field-${field.name}`"
          :model-value="Boolean(modelValue[field.name])"
          :label="field.label"
          :disable="disable"
          @update:model-value="update(field.name, $event)"
        />

        <!-- choices is optional on FieldSpec, and the untyped q-select used to
           accept undefined without a word. -->
        <AppSelect
          v-else-if="field.kind === 'select'"
          :data-testid="`field-${field.name}`"
          :model-value="modelValue[field.name]"
          :options="field.choices ?? []"
          :label="field.label"
          :error="errors[field.name]"
          :disable="disable"
          @update:model-value="update(field.name, $event)"
        />

        <!-- A number reports a number and an emptied field reports null, so no
           screen has to coerce what the control gives back. -->
        <AppNumberInput
          v-else-if="field.kind === 'number'"
          :data-testid="`field-${field.name}`"
          :model-value="numberValue(field.name)"
          :label="field.label"
          :error="errors[field.name]"
          :disable="disable"
          @update:model-value="update(field.name, $event)"
        />

        <!-- A stored secret shows as plain text on purpose: dots would say a
             password of eight characters is there, and what is there is
             unknown to this screen. Editable rather than read-only, because
             Quasar does not report focus on a field it considers uneditable —
             and focus is the moment the stand-in gives way. -->
        <AppInput
          v-else
          :data-testid="`field-${field.name}`"
          :model-value="isHidden(field) ? HIDDEN : textValue(field.name)"
          :label="field.label"
          :type="field.kind === 'password' && !isHidden(field) ? 'password' : 'text'"
          :error="errors[field.name]"
          :disable="disable"
          @focus="field.kind === 'password' ? reveal(field.name) : undefined"
          @blur="field.kind === 'password' ? restore(field.name) : undefined"
          @update:model-value="update(field.name, $event)"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
.schema-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
/* Every field on a line gets the same share, except that a field with a
   narrow value — a port — is not made to take half the width of an address. */
.schema-fields__row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.schema-fields__row > * {
  flex: 1;
  min-width: 0;
}
.schema-fields__row > * + * {
  flex: 0 0 30%;
}
</style>
