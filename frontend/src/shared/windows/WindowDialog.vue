<script setup lang="ts">
import { computed, defineComponent, getCurrentInstance, h, onBeforeUnmount, useAttrs, useSlots, watch } from "vue"

import AppActions from "@/shared/ui/AppActions.vue"

import { useWindowManager } from "./useWindows"

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    title: string
    subtitle?: string
    size?: "sm" | "md" | "lg" | "xl" | "form" | "compact-form"
    sizing?: "content" | "stable"
    /**
     * Whether the window may close, asked before it does.
     *
     * The host already supports it; a dialog holding unsaved work is the
     * reason to pass it on — closing a draft by the frame's own X has to ask
     * the same question the Cancel button does.
     */
    beforeClose?: () => boolean | Promise<boolean>
  }>(),
  { subtitle: undefined, size: "md", sizing: "content", beforeClose: undefined }
)

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()
defineOptions({ inheritAttrs: false })

const windows = useWindowManager()
const slots = useSlots()
const attrs = useAttrs()
const instance = getCurrentInstance()
const id = `dialog:${String(attrs["data-testid"] ?? props.title)}:${instance?.uid ?? 0}`

const sizes = {
  "compact-form": { width: 560, height: 360 },
  // Variable-content forms keep room for optional fields and inline errors.
  form: { width: 560, height: 580 },
  sm: { width: 460, height: 220 },
  md: { width: 520, height: 260 },
  lg: { width: 900, height: 360 },
  // An editor rather than a form: the object tree, the inspector and the SQL
  // preview are three panes, and lg puts them in 300 pixels each.
  xl: { width: 1120, height: 680 },
} as const

const component = defineComponent({
  name: `WindowDialogContent-${instance?.uid ?? 0}`,
  setup: () => () =>
    h(
      "div",
      { ...attrs, class: ["window-dialog", attrs.class, { "window-dialog--stable": props.sizing === "stable" }] },
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
      sizing: props.sizing,
      minSize: { width: 300, height: 140 },
      component,
      ...(props.beforeClose === undefined ? {} : { beforeClose: props.beforeClose }),
      onClosed: () => emit("update:modelValue", false),
    })
  },
  { immediate: true }
)

// The heading follows the form. It is opened with the title of the moment,
// and a dialog whose subject changes while it is open — a destination that
// decides whether this is a table or a file — must not keep the first word.
watch(
  () => props.title,
  (title) => {
    if (windows.isOpen(id)) windows.retitle(id, { title })
  }
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
.window-dialog--stable {
  flex: 1;
}
.window-dialog--stable .window-dialog__content {
  flex: 1;
}
.window-dialog__subtitle {
  flex: none;
  padding: var(--dp-space-2) var(--dp-space-4) 0;
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
