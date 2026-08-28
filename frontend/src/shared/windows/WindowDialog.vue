<script setup lang="ts">
import { computed, defineComponent, getCurrentInstance, h, onBeforeUnmount, useAttrs, useSlots, watch } from "vue"

import AppActions from "@/shared/ui/AppActions.vue"

import { useWindowManager } from "./useWindows"

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    title: string
    subtitle?: string
    size?: "sm" | "md" | "lg"
  }>(),
  { subtitle: undefined, size: "md" }
)

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()
defineOptions({ inheritAttrs: false })

const windows = useWindowManager()
const slots = useSlots()
const attrs = useAttrs()
const instance = getCurrentInstance()
const id = `dialog:${String(attrs["data-testid"] ?? props.title)}:${instance?.uid ?? 0}`

const sizes = {
  sm: { width: 460, height: 220 },
  md: { width: 520, height: 260 },
  lg: { width: 900, height: 360 },
} as const

const component = defineComponent({
  name: `WindowDialogContent-${instance?.uid ?? 0}`,
  setup: () => () =>
    h(
      "div",
      { class: "window-dialog", ...attrs },
      [
        props.subtitle
          ? h("div", { class: "window-dialog__subtitle" }, props.subtitle)
          : null,
        h("div", { class: "window-dialog__content" }, slots.default?.()),
        slots.actions
          ? h(AppActions, { class: "window-dialog__actions" }, { default: slots.actions })
          : null,
      ]
    ),
})

const openSize = computed(() => sizes[props.size])

watch(
  () => props.modelValue,
  (open) => {
    if (!open) {
      if (windows.isOpen(id)) windows.close(id)
      return
    }
    windows.open({
      id,
      look: { title: props.title },
      size: openSize.value,
      minSize: { width: 300, height: 140 },
      component,
      onClosed: () => emit("update:modelValue", false),
    })
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (windows.isOpen(id)) windows.close(id)
})
</script>

<template>
  <!-- The content is rendered by WindowHost; this component only owns its lifecycle. -->
  <span class="window-dialog-anchor" />
</template>

<style>
.window-dialog-anchor {
  display: none;
}
.window-dialog {
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: calc(100vh - 34px);
}
.window-dialog__subtitle {
  flex: none;
  padding: 8px 16px 0;
  color: var(--dp-text-muted);
  font-size: 0.75rem;
}
.window-dialog__content {
  min-height: 0;
  overflow: auto;
}
.window-dialog__actions {
  flex: none;
  border-top: 1px solid var(--dp-border);
}
</style>
