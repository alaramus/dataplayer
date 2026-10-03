<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, useTemplateRef, watch } from "vue"

import AppOption from "./AppOption.vue"
import AppPopup from "./AppPopup.vue"
import type { SelectOption } from "./AppSelect.vue"
import { appIcons } from "./icons"

/**
 * A field whose words are answered by a grouped list under it (D205).
 *
 * The focus never leaves the field: the list opens without taking it, and the
 * row being pointed at is the field's `aria-activedescendant`. No row is
 * active until an arrow is pressed, so Enter on the words alone is the field's
 * own answer — `submit` — and never the first row's by accident.
 *
 * The rows are AppSelect's options, drawn by the same AppOption: a heading
 * starts a group, and a row has its icon, its second line and the action of
 * its own — pressed, or Ctrl+Enter (⌘Enter) on the active row, as a found file
 * is revealed where it lives rather than opened.
 */
const props = withDefaults(
  defineProps<{
    modelValue: string
    options: readonly SelectOption[]
    /** What the field is called for a reader: it has no label of its own. */
    label: string
    placeholder?: string
    /** What is still being asked and what did not answer, said politely. */
    status?: string
    /** What the words are limited to, drawn before them. Backspace removes it. */
    chip?: string | null
    /** The last row, which asks for everything rather than one row. */
    submitLabel?: string
    /** Rows drawn after the last one and kept in sight with it; each is picked. */
    trailing?: readonly SelectOption[]
    /** How tall the rows may grow before they scroll; the last row and the status stay below them. */
    maxHeight?: string
  }>(),
  {
    placeholder: undefined,
    status: "",
    chip: null,
    submitLabel: undefined,
    trailing: () => [],
    maxHeight: "min(420px, 55vh)",
  }
)

const open = defineModel<boolean>("open", { default: false })

const emit = defineEmits<{
  "update:modelValue": [value: string]
  /** A row was taken: Enter on it, a press, or the right arrow on an offer. */
  pick: [value: string | number]
  /** A row's own action: its button, or Ctrl+Enter (⌘Enter) on it. */
  action: [value: string | number]
  /** Enter with no row active, or the last row. */
  submit: []
  /** Backspace before the first word, with a chip there to take away. */
  "remove-chip": []
  /** Escape with no list shown: the person is leaving the field. */
  leave: []
}>()

interface Row {
  option: SelectOption
  id: string
  /** The last row, which submits rather than picks. */
  submits: boolean
}

interface Section {
  heading: SelectOption | null
  headingId: string
  rows: Row[]
}

const listId = useId()
const input = useTemplateRef<HTMLInputElement>("input")
const root = useTemplateRef<HTMLElement>("root")

/**
 * One id per value for as long as the field lives, so the row an arrow stood
 * on keeps its id when the list is drawn again, and loses it only when its
 * value is gone. A value is not used as the id itself: an id reference may
 * hold no space, and a file's path may.
 */
const ids = new Map<string | number, string>()
function idOf(value: string | number): string {
  let id = ids.get(value)
  if (id === undefined) {
    id = `${listId}-option-${String(ids.size)}`
    ids.set(value, id)
  }
  return id
}

/**
 * The list is as wide as the field, never wider: a menu takes the width of
 * its widest row, and one long path stretched it to the edge of the window.
 */
const width = ref<string | undefined>(undefined)
let observer: ResizeObserver | null = null
onMounted(() => {
  if (root.value === null || typeof ResizeObserver === "undefined") return
  observer = new ResizeObserver((entries) => {
    const box = entries[0]?.borderBoxSize[0]
    if (box !== undefined) width.value = `${String(Math.round(box.inlineSize))}px`
  })
  observer.observe(root.value)
})
onBeforeUnmount(() => observer?.disconnect())

const sections = computed<Section[]>(() => {
  const found: Section[] = []
  let current: Section | null = null
  for (const option of props.options) {
    if (option.group) {
      current = { heading: option, headingId: `${listId}-heading-${String(found.length)}`, rows: [] }
      found.push(current)
      continue
    }
    if (current === null) {
      current = { heading: null, headingId: "", rows: [] }
      found.push(current)
    }
    current.rows.push({ option, id: idOf(option.value), submits: false })
  }
  return found
})

/** The last rows, kept in sight under the others however far they scroll. */
const closing = computed<Row[]>(() => [
  ...(props.submitLabel === undefined
    ? []
    : [{
        option: { label: props.submitLabel, value: `${listId}-submit`, icon: appIcons.search },
        id: `${listId}-submit`,
        submits: true,
      }]),
  ...props.trailing.map((option) => ({ option, id: idOf(option.value), submits: false })),
])

/** The rows an arrow can stand on, in the order they are drawn. */
const rows = computed(() => [
  ...sections.value.flatMap((section) => section.rows).filter((row) => !row.option.disable),
  ...closing.value,
])

/** Which row is active, by id so that a list drawn again keeps or loses it honestly. */
const activeId = ref<string | null>(null)
const activeRow = computed(() => rows.value.find((row) => row.id === activeId.value) ?? null)

watch(rows, (now) => {
  if (activeId.value !== null && !now.some((row) => row.id === activeId.value)) {
    activeId.value = null
  }
})

const shown = computed(
  () => open.value && (rows.value.length > 0 || props.status !== "")
)

function move(step: 1 | -1) {
  const list = rows.value
  if (list.length === 0) return
  const at = list.findIndex((row) => row.id === activeId.value)
  const next = at === -1 ? (step === 1 ? 0 : list.length - 1) : (at + step + list.length) % list.length
  activeId.value = list[next]?.id ?? null
  void nextTick(() => {
    if (activeId.value !== null) {
      document.getElementById(activeId.value)?.scrollIntoView({ block: "nearest" })
    }
  })
}

function take(row: Row) {
  if (row.submits) emit("submit")
  else emit("pick", row.option.value)
}

function caretAt(position: "start" | "end"): boolean {
  const field = input.value
  if (field === null) return false
  const at = position === "start" ? 0 : field.value.length
  return field.selectionStart === at && field.selectionEnd === at
}

function onKeydown(event: KeyboardEvent) {
  if (event.isComposing) return
  switch (event.key) {
    case "ArrowDown":
    case "ArrowUp":
      event.preventDefault()
      if (!open.value) {
        open.value = true
        return
      }
      move(event.key === "ArrowDown" ? 1 : -1)
      return
    case "Enter": {
      event.preventDefault()
      const row = shown.value ? activeRow.value : null
      // Either modifier, on every platform: neither does anything else in a
      // field, and a Mac keyboard on Windows still says ⌘. Where the row has
      // no action of its own, it is Enter.
      if ((event.ctrlKey || event.metaKey) && row?.option.actionIcon !== undefined) {
        emit("action", row.option.value)
        return
      }
      if (row !== null) take(row)
      else emit("submit")
      return
    }
    case "Escape":
      // Not handed on: Quasar closes its topmost menu on an Escape that
      // reaches the window, and the second Escape is this field's own.
      event.preventDefault()
      event.stopPropagation()
      activeId.value = null
      if (shown.value) {
        open.value = false
      } else {
        open.value = false
        emit("leave")
      }
      return
    case "ArrowRight": {
      if (!shown.value || !caretAt("end")) return
      const offer = rows.value[0]
      if (offer === undefined || offer.option.offer !== true) return
      event.preventDefault()
      take(offer)
      return
    }
    case "Backspace":
      if (props.chip === null || !caretAt("start")) return
      event.preventDefault()
      emit("remove-chip")
      return
  }
}

function onInput(event: Event) {
  emit("update:modelValue", (event.target as HTMLInputElement).value)
  activeId.value = null
  open.value = true
}

defineExpose({
  focus: () => input.value?.focus(),
  /** Every word selected, so the next key replaces them. */
  select: () => input.value?.select(),
})
</script>

<template>
  <div
    ref="root"
    class="app-combobox"
    :class="{ 'app-combobox--open': shown }"
  >
    <q-icon
      :name="appIcons.search"
      class="app-combobox__icon"
      size="var(--dp-icon-sm)"
    />
    <span
      v-if="chip !== null"
      class="app-combobox__chip"
      data-testid="combobox-chip"
    >{{ chip }}</span>
    <input
      ref="input"
      class="app-combobox__input"
      type="text"
      role="combobox"
      autocomplete="off"
      spellcheck="false"
      aria-autocomplete="list"
      :aria-label="label"
      :aria-expanded="shown ? 'true' : 'false'"
      :aria-controls="listId"
      :aria-activedescendant="shown && activeId !== null ? activeId : undefined"
      :placeholder="placeholder"
      :value="modelValue"
      @input="onInput"
      @keydown="onKeydown"
      @click="open = true"
    >
    <slot name="after" />
    <!-- Out of the list, and always there: a live region that appears with
         what it says is not read out. -->
    <span
      class="app-combobox__live"
      role="status"
    >{{ status }}</span>
    <AppPopup
      :model-value="shown"
      no-focus
      no-refocus
      no-parent-event
      fit
      :max-width="width"
      role="presentation"
      @update:model-value="(value: boolean) => { if (!value) open = false }"
    >
      <!-- A press on a row must not take the focus from the field. -->
      <div
        :id="listId"
        role="listbox"
        :aria-label="label"
        class="app-combobox__list"
        @mousedown.prevent
      >
        <div
          class="app-combobox__rows"
          :style="{ maxHeight }"
        >
          <div
            v-for="(section, at) in sections"
            :key="at"
            role="group"
            :aria-labelledby="section.heading ? section.headingId : undefined"
          >
            <AppOption
              v-if="section.heading"
              :id="section.headingId"
              role="presentation"
              :option="section.heading"
            />
            <AppOption
              v-for="row in section.rows"
              :id="row.id"
              :key="row.id"
              role="option"
              :aria-selected="row.id === activeId ? 'true' : 'false'"
              :aria-disabled="row.option.disable ? 'true' : undefined"
              :option="row.option"
              :class="{ 'app-combobox__row--active': row.id === activeId }"
              clickable
              manual-focus
              :focused="row.id === activeId"
              :disable="row.option.disable"
              :tabindex="-1"
              dense
              @click="take(row)"
              @action="emit('action', row.option.value)"
            />
          </div>
        </div>
        <div
          v-if="closing.length > 0"
          role="group"
          class="app-combobox__closing"
        >
          <AppOption
            v-for="row in closing"
            :id="row.id"
            :key="row.id"
            role="option"
            :aria-selected="row.id === activeId ? 'true' : 'false'"
            :option="row.option"
            :class="{ 'app-combobox__row--active': row.id === activeId }"
            clickable
            manual-focus
            :focused="row.id === activeId"
            :tabindex="-1"
            dense
            @click="take(row)"
          />
        </div>
      </div>
      <div
        v-if="status"
        class="app-combobox__status"
        aria-hidden="true"
      >
        {{ status }}
      </div>
    </AppPopup>
  </div>
</template>

<style scoped>
.app-combobox {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  min-width: 0;
  height: var(--dp-control-height);
  padding: 0 var(--dp-space-2);
  border: 1px solid var(--dp-field-border);
  border-radius: var(--dp-radius-control);
  background: var(--dp-field-surface);
  color: var(--dp-text);
}
.app-combobox:focus-within {
  border-color: var(--dp-focus-border);
}
.app-combobox__icon {
  flex: none;
  color: var(--dp-text-muted);
}
.app-combobox__input {
  flex: 1;
  min-width: 0;
  padding: 0;
  border: none;
  outline: none;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: var(--dp-font-size);
}
.app-combobox__input::placeholder {
  color: var(--dp-text-muted);
}
/* What the words are limited to, as a token of the field rather than words
   in it: one Backspace takes it away whole. */
.app-combobox__chip {
  flex: 0 1 auto;
  max-width: 50%;
  overflow: hidden;
  padding: 0 var(--dp-space-2);
  border-radius: var(--dp-radius-pill);
  background: var(--dp-selected-quiet);
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-combobox__live {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.app-combobox__rows {
  overflow-y: auto;
  padding: var(--dp-space-1) 0;
}
/* One line a row, cut rather than wrapped: a long path pushed the next row
   down by a line only it needed. */
.app-combobox__list :deep(.app-option__line) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Where the arrows stand, plainly: the focus stays in the field, so the
   row has no focus of its own to be drawn with. */
.app-combobox__row--active {
  background: var(--dp-selected);
}
.app-combobox__closing {
  border-top: 1px solid var(--dp-border-faint);
}
.app-combobox__status {
  padding: var(--dp-space-1) var(--dp-space-3);
  border-top: 1px solid var(--dp-border-faint);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
}
</style>
