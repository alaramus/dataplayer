<script setup lang="ts">
import { nextTick, ref } from "vue"

import { AppIconButton, AppInput } from "@/shared/ui"

import { MAX_TITLE } from "./dashboardModel"

/**
 * The frame every widget wears: its title, renamed in place by a double click,
 * and the commands about the widget itself. The header is what a widget is
 * carried by, so the grid listens to presses on it.
 */
const props = defineProps<{
  title: string
  expanded: boolean
  /** A read that failed, said inside the frame rather than instead of it. */
  error?: string | null
  /** Whether it may be moved, resized, renamed and removed: not on a dashboard one may only view. */
  editable?: boolean
}>()

const emit = defineEmits<{
  rename: [title: string]
  remove: []
  toggleExpand: []
  detach: []
  grab: [event: PointerEvent]
  grabResize: [event: PointerEvent]
}>()

const editing = ref(false)
const draft = ref("")
const field = ref<InstanceType<typeof AppInput> | null>(null)

async function startRename() {
  if (props.editable === false) return
  draft.value = props.title
  editing.value = true
  await nextTick()
  const input = (field.value?.$el as HTMLElement | undefined)?.querySelector("input")
  input?.focus()
  input?.select()
}

function commit() {
  if (!editing.value) return
  editing.value = false
  const title = draft.value.trim()
  if (title !== "" && title !== props.title) emit("rename", title.slice(0, MAX_TITLE))
}

function onHeaderPointerDown(event: PointerEvent) {
  if (editing.value || props.expanded || props.editable === false) return
  if ((event.target as HTMLElement).closest("button, input") !== null) return
  emit("grab", event)
}
</script>

<template>
  <div
    class="widget-frame"
    data-testid="widget"
  >
    <div
      class="widget-frame__header"
      @pointerdown="onHeaderPointerDown"
      @dblclick="startRename"
    >
      <AppInput
        v-if="editing"
        ref="field"
        v-model="draft"
        class="widget-frame__title-input"
        compact
        aria-label="Widget title"
        @keydown.enter="commit"
        @keydown.esc="editing = false"
        @blur="commit"
      />
      <span
        v-else
        class="widget-frame__title"
        :title="editable === false ? title : `${title} — double-click to rename`"
      >{{ title }}</span>
      <AppIconButton
        icon="open_in_new"
        tooltip="Open in a window, over the data as well"
        compact
        data-testid="widget-detach"
        @click="emit('detach')"
      />
      <AppIconButton
        :icon="expanded ? 'close_fullscreen' : 'open_in_full'"
        :tooltip="expanded ? 'Back to the dashboard' : 'Fill the dashboard with this widget'"
        compact
        @click="emit('toggleExpand')"
      />
      <AppIconButton
        v-if="editable !== false"
        icon="close"
        tooltip="Remove this widget"
        compact
        data-testid="widget-remove"
        @click="emit('remove')"
      />
    </div>
    <div class="widget-frame__body">
      <div
        v-if="error"
        class="widget-frame__error"
      >
        {{ error }}
      </div>
      <slot v-else />
    </div>
    <div
      v-if="!expanded && editable !== false"
      class="widget-frame__resize"
      title="Drag to resize"
      @pointerdown.stop="emit('grabResize', $event)"
    />
  </div>
</template>

<style scoped>
.widget-frame {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  background: var(--dp-surface);
  overflow: hidden;
}

.widget-frame__header {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  min-height: var(--dp-tab-strip-height);
  padding: 0 var(--dp-space-1) 0 var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
  cursor: grab;
  user-select: none;
  touch-action: none;
}

.widget-frame__title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--dp-text-strong);
}

.widget-frame__title-input {
  flex: 1;
  min-width: 0;
}

.widget-frame__body {
  flex: 1;
  min-height: 0;
  padding: var(--dp-space-2);
}

.widget-frame__error {
  color: var(--dp-text-muted);
}

.widget-frame__resize {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 14px;
  height: 14px;
  cursor: nwse-resize;
  touch-action: none;
  background: linear-gradient(135deg, transparent 50%, var(--dp-border-strong) 50%);
}
</style>
