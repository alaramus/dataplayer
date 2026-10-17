<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useAttrs, useTemplateRef } from "vue"

import AppIconButton from "./AppIconButton.vue"

/**
 * A button drawn as the field it opens, with the keys that open it too: the
 * search in the header (D205).
 *
 * It takes the room it is given and gives way to an icon when that room is
 * narrower than the field — measured where it stands, not guessed from the
 * window, because what is beside it in a header (a waiting pair, D167) takes
 * a width no breakpoint knows.
 */
const props = defineProps<{
  label: string
  icon: string
  /** The keys as a person reads them: "Ctrl + K", "⌘ + K". */
  keys?: string
  /** The same keys for a reader, as `aria-keyshortcuts` spells them. */
  keyshortcuts?: string
}>()

const emit = defineEmits<{ click: [] }>()

// Both shapes are the one control: what names it lands on whichever is drawn.
defineOptions({ inheritAttrs: false })
const attrs = useAttrs()

/** The narrowest the field is drawn; below it, the icon. */
const FIELD_MIN_WIDTH = 160

const room = useTemplateRef<HTMLElement>("room")
const narrow = ref(false)
let observer: ResizeObserver | null = null

onMounted(() => {
  if (room.value === null || typeof ResizeObserver === "undefined") return
  observer = new ResizeObserver((entries) => {
    const width = entries[0]?.contentRect.width
    if (width !== undefined) narrow.value = width < FIELD_MIN_WIDTH
  })
  observer.observe(room.value)
})
onBeforeUnmount(() => observer?.disconnect())

const tooltip = props.keys ? `${props.label} (${props.keys})` : props.label
</script>

<template>
  <div
    ref="room"
    class="app-field-button"
  >
    <AppIconButton
      v-if="narrow"
      v-bind="attrs"
      :icon="icon"
      :tooltip="tooltip"
      :aria-keyshortcuts="keyshortcuts"
      @click="emit('click')"
    />
    <button
      v-else
      v-bind="attrs"
      type="button"
      class="app-field-button__field"
      :style="{ minWidth: `${FIELD_MIN_WIDTH}px` }"
      :aria-keyshortcuts="keyshortcuts"
      @click="emit('click')"
    >
      <q-icon
        :name="icon"
        size="var(--dp-icon-sm)"
        class="app-field-button__icon"
      />
      <span class="app-field-button__label">{{ label }}</span>
      <kbd
        v-if="keys"
        class="app-field-button__keys"
        aria-hidden="true"
      >{{ keys }}</kbd>
    </button>
  </div>
</template>

<style scoped>
/* The whole room it stands in, so what it measures is that room. */
.app-field-button {
  display: flex;
  flex: 1 1 auto;
  justify-content: center;
  min-width: 0;
}
.app-field-button__field {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  width: 100%;
  max-width: var(--dp-width-popover);
  height: var(--dp-control-height);
  padding: 0 var(--dp-space-2);
  border: 1px solid var(--dp-field-border);
  border-radius: var(--dp-radius-control);
  background: var(--dp-field-surface);
  color: var(--dp-text-muted);
  font: inherit;
  font-size: var(--dp-font-size);
  cursor: pointer;
}
.app-field-button__field:hover {
  border-color: var(--dp-border-strong);
}
.app-field-button__field:focus-visible {
  border-color: var(--dp-focus-border);
  outline: none;
}
.app-field-button__icon {
  flex: none;
}
.app-field-button__label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-field-button__keys {
  flex: none;
  padding: 0 var(--dp-space-1);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
  color: var(--dp-text-muted);
  font-family: inherit;
  font-size: var(--dp-font-size-xs);
  line-height: var(--dp-line-height-sm);
}
</style>
