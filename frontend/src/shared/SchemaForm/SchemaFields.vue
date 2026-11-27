<script setup lang="ts">
import { computed, inject, ref, watch } from "vue"
import { t } from "@/shared/i18n"
import { formLayoutKey } from "@/shared/ui/formLayout"

import AppDateTimeInput from "@/shared/ui/AppDateTimeInput.vue"
import AppIconButton from "@/shared/ui/AppIconButton.vue"
import AppInput from "@/shared/ui/AppInput.vue"
import AppNumberInput from "@/shared/ui/AppNumberInput.vue"
import AppSelect from "@/shared/ui/AppSelect.vue"
import AppToggle from "@/shared/ui/AppToggle.vue"
import AppTooltip from "@/shared/ui/AppTooltip.vue"
import { appIcons } from "@/shared/ui/icons"

import { droppedFile, readFieldFile } from "./fieldFile"
import { autofillOf, fieldRows } from "./jsonSchema"
import type { FieldSpec } from "./jsonSchema"

const formLayout = inject(formLayoutKey, false)

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

/**
 * A field whose purpose the screen knows better than a box does.
 *
 * `field-<purpose>` draws it instead of the ordinary control, with the value
 * and a way to change it: the key a server proved itself with is compared and
 * trusted rather than typed (D145). The form stays generic — it knows there
 * is a slot, never what a purpose means.
 */
const slots = defineSlots<{
  [name: `field-${string}`]: (props: {
    field: FieldSpec
    value: unknown
    disable: boolean
    update: (value: unknown) => void
  }) => unknown
}>()

function update(name: string, value: unknown) {
  emit("update:modelValue", { ...props.modelValue, [name]: value })
}

// Lines rather than a flat column: which fields share one is decided by the
// model that declares them and arrives in the schema.
// A line holding only hidden fields draws nothing, and is left out so its gap
// does not open between the lines around it.
const rows = computed(() =>
  fieldRows(props.fields).filter((row) => row.some((field) => field.kind !== "hidden"))
)

function textValue(name: string): string {
  const value = props.modelValue[name]
  return value === null || value === undefined ? "" : String(value)
}

function numberValue(name: string): number | null {
  const value = props.modelValue[name]
  return typeof value === "number" ? value : null
}

/**
 * What the control is, once a stand-in for a secret is taken into account.
 *
 * The kind says what the value is; only this screen knows whether it is
 * currently showing the value or the words standing in for one, and a
 * stand-in is plain text however the field is normally drawn.
 */
function inputType(field: FieldSpec): "text" | "password" | "textarea" {
  if (field.kind === "password") {
    return isHidden(field) || visiblePasswords.value.has(field.name) ? "text" : "password"
  }
  return field.kind === "multiline" ? "textarea" : "text"
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
const hidden = computed(() => t("schema_form.hidden"))

const touched = ref<Set<string>>(new Set())
const visiblePasswords = ref<Set<string>>(new Set())

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

function togglePassword(name: string) {
  const next = new Set(visiblePasswords.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  visiblePasswords.value = next
}

/**
 * What the form is showing, as a signature that survives a re-render.
 *
 * A parent hands over a new array of fields whenever it recomputes them, and
 * one recomputes on every keystroke: the connection form derives a tunnel's
 * choices from the values it holds. Resetting on the identity of that array
 * hid a password the moment it was typed into — the eye had been pressed and
 * the field went back to dots. Only a different set of fields is a different
 * set of secrets.
 */
const fieldSignature = computed(() =>
  props.fields.map((field) => `${field.group}:${field.name}:${field.kind}`).join("\u0000")
)

// A different set of fields — another way of connecting, another source — is
// a different set of secrets.
watch(
  () => [fieldSignature.value, props.secretsAreStored],
  () => {
    touched.value = new Set()
    visiblePasswords.value = new Set()
  }
)
/**
 * Whether a field shares its line with another, as a port shares the host's.
 *
 * Its description then goes behind an icon beside it: a sentence under a
 * narrow field wraps into four lines and opens a gap under the whole row.
 */
function sharesLine(row: FieldSpec[]): boolean {
  return row.filter((field) => field.kind !== "hidden").length > 1
}

function hintOf(field: FieldSpec, row: FieldSpec[]): string | undefined {
  return sharesLine(row) ? undefined : field.description
}

function tipOf(field: FieldSpec, row: FieldSpec[]): string | undefined {
  return sharesLine(row) && field.description ? field.description : undefined
}

/**
 * Why the file last chosen for a field was not read, until the field changes.
 *
 * Kept here rather than among the parent's errors: those answer what the
 * server said about a value, and this value never left the page.
 */
const fileErrors = ref<Record<string, string>>({})

function errorOf(field: FieldSpec): string | undefined {
  return props.errors[field.name] || fileErrors.value[field.name] || undefined
}

function edit(name: string, value: unknown) {
  if (fileErrors.value[name] !== undefined) {
    fileErrors.value = Object.fromEntries(
      Object.entries(fileErrors.value).filter(([field]) => field !== name)
    )
  }
  update(name, value)
}

/**
 * The one native picker, opened by whichever field's button was pressed.
 *
 * Trap: it lives outside the fields. Inside a QField the click that opens it
 * bubbles to the field, which cancels it, and the picker never shows.
 */
const picker = ref<HTMLInputElement | null>(null)
const picking = ref<FieldSpec | null>(null)

function pick(field: FieldSpec) {
  const input = picker.value
  if (input === null) return
  picking.value = field
  // Set on the element rather than bound: a binding lands after the click.
  input.accept = field.file ?? ""
  input.click()
}

// A file's text replaces the value, exactly as a paste would, and a stored
// secret's stand-in gives way to it: what was read is what will be saved.
async function readInto(field: FieldSpec, file: File) {
  try {
    const text = await readFieldFile(file, field.label, field.maxLength)
    touched.value = new Set(touched.value).add(field.name)
    edit(field.name, text)
  } catch (cause) {
    fileErrors.value = {
      ...fileErrors.value,
      [field.name]: cause instanceof Error ? cause.message : String(cause),
    }
  }
}

function picked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  // Emptied so that choosing the same file again, after fixing it, reads it again.
  input.value = ""
  const field = picking.value
  if (file !== undefined && field !== null) void readInto(field, file)
}

// Only a drag carrying files is taken over: text dragged onto the box still
// lands in it the way the browser puts it there.
function dragOver(field: FieldSpec, event: DragEvent) {
  if (props.disable || field.file === undefined) return
  if (event.dataTransfer?.types.includes("Files") !== true) return
  event.preventDefault()
  event.dataTransfer.dropEffect = "copy"
}

function dropped(field: FieldSpec, event: DragEvent) {
  if (props.disable || field.file === undefined) return
  if (event.dataTransfer?.types.includes("Files") !== true) return
  event.preventDefault()
  const file = droppedFile(event.dataTransfer)
  if (file !== null) void readInto(field, file)
}
</script>

<template>
  <div
    class="schema-fields"
    :class="{ 'schema-fields--form': formLayout }"
  >
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
        <slot
          v-else-if="field.purpose && slots[`field-${field.purpose}`]"
          :name="`field-${field.purpose}`"
          :field="field"
          :value="modelValue[field.name]"
          :disable="disable === true"
          :update="(value: unknown) => update(field.name, value)"
        />
        <!-- The one control with no line under it: a toggle's label is
             already the whole statement — "Replace it if it already exists" —
             and a model that wants to say more says it there. -->
        <AppToggle
          v-else-if="field.kind === 'boolean'"
          :data-testid="`field-${field.name}`"
          :model-value="Boolean(modelValue[field.name])"
          :label="field.label"
          :disable="disable"
          @update:model-value="update(field.name, $event)"
        />

        <!-- choices is optional on FieldSpec, and the untyped q-select used to
           accept undefined without a word. A select shows no example: what a
           filled one looks like is the list it offers.
           Trap: no autocomplete here. Given one, QSelect draws a hidden input
           for the browser's autofill over its 1px combobox, and a click on the
           combobox lands on that input instead. -->
        <AppSelect
          v-else-if="field.kind === 'select'"
          :data-testid="`field-${field.name}`"
          :model-value="modelValue[field.name]"
          :options="field.choices ?? []"
          :label="field.label"
          :hint="hintOf(field, row)"
          :error="errors[field.name]"
          :disable="disable"
          @update:model-value="update(field.name, $event)"
        >
          <template
            v-if="tipOf(field, row)"
            #after
          >
            <q-icon
              :name="appIcons.info"
              class="schema-fields__tip"
              tabindex="0"
              :aria-label="tipOf(field, row)"
              :data-testid="`field-${field.name}-tip`"
            >
              <AppTooltip>{{ tipOf(field, row) }}</AppTooltip>
            </q-icon>
          </template>
        </AppSelect>

        <!-- A number reports a number and an emptied field reports null, so no
           screen has to coerce what the control gives back. -->
        <AppNumberInput
          v-else-if="field.kind === 'number'"
          :data-testid="`field-${field.name}`"
          :autocomplete="autofillOf(field)"
          :model-value="numberValue(field.name)"
          :label="field.label"
          :hint="hintOf(field, row)"
          :placeholder="field.example"
          :error="errors[field.name]"
          :disable="disable"
          @update:model-value="update(field.name, $event)"
        >
          <template
            v-if="tipOf(field, row)"
            #after
          >
            <q-icon
              :name="appIcons.info"
              class="schema-fields__tip"
              tabindex="0"
              :aria-label="tipOf(field, row)"
              :data-testid="`field-${field.name}-tip`"
            >
              <AppTooltip>{{ tipOf(field, row) }}</AppTooltip>
            </q-icon>
          </template>
        </AppNumberInput>

        <AppDateTimeInput
          v-else-if="field.kind === 'datetime'"
          :data-testid="`field-${field.name}`"
          :model-value="textValue(field.name)"
          :label="field.label"
          :hint="field.description"
          :placeholder="field.example"
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
          :autocomplete="autofillOf(field)"
          :model-value="isHidden(field) ? hidden : textValue(field.name)"
          :label="field.label"
          :hint="hintOf(field, row)"
          :placeholder="field.example"
          :type="inputType(field)"
          :error="errorOf(field)"
          :disable="disable"
          @focus="field.kind === 'password' ? reveal(field.name) : undefined"
          @blur="field.kind === 'password' ? restore(field.name) : undefined"
          @update:model-value="edit(field.name, $event)"
          @dragover="dragOver(field, $event)"
          @drop="dropped(field, $event)"
        >
          <template
            v-if="field.kind === 'password' || field.file !== undefined || tipOf(field, row)"
            #after
          >
            <q-icon
              v-if="tipOf(field, row)"
              :name="appIcons.info"
              class="schema-fields__tip"
              tabindex="0"
              :aria-label="tipOf(field, row)"
              :data-testid="`field-${field.name}-tip`"
            >
              <AppTooltip>{{ tipOf(field, row) }}</AppTooltip>
            </q-icon>
            <AppIconButton
              v-if="field.kind === 'password'"
              :icon="
                visiblePasswords.has(field.name) ? appIcons.visibilityOff : appIcons.visibility
              "
              :tooltip="
                visiblePasswords.has(field.name)
                  ? t('schema_form.hide_password')
                  : t('schema_form.show_password')
              "
              :disable="disable || textValue(field.name) === '' || isHidden(field)"
              :data-testid="`field-${field.name}-visibility`"
              @click="togglePassword(field.name)"
            />
            <AppIconButton
              v-if="field.file !== undefined"
              :icon="appIcons.fromFile"
              :tooltip="t('schema_form.from_file', { label: field.label })"
              :disable="disable"
              :data-testid="`field-${field.name}-from-file`"
              @click="pick(field)"
            />
          </template>
        </AppInput>
      </template>
    </div>
    <input
      v-if="fields.some((field) => field.file !== undefined)"
      ref="picker"
      type="file"
      class="schema-fields__picker"
      tabindex="-1"
      aria-hidden="true"
      data-testid="schema-fields-file"
      @change="picked"
    >
  </div>
</template>

<style scoped>
.schema-fields {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-4);
}
/* Every field on a line gets the same share, except that a field with a
   narrow value — a port — is not made to take half the width of an address. */
.schema-fields__row {
  display: flex;
  gap: var(--dp-space-3);
  align-items: flex-start;
}
.schema-fields__row > * {
  flex: 1;
  min-width: 0;
}
.schema-fields__row > * + * {
  flex: 0 0 30%;
}
.schema-fields--form .schema-fields__row > * + * {
  --dp-form-label-width: auto;
}
.schema-fields__picker {
  display: none;
}
.schema-fields__tip {
  font-size: var(--dp-icon-sm);
  color: var(--dp-text-muted);
  cursor: help;
}
@container app-form (max-width: 480px) {
  .schema-fields--form .schema-fields__row {
    flex-direction: column;
  }
  .schema-fields--form .schema-fields__row > * {
    flex: auto;
    width: 100%;
  }
}
</style>
