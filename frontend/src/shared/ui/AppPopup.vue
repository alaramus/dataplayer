<script setup lang="ts">
import { onBeforeUnmount, useTemplateRef } from "vue"

import type { QMenuProps } from "quasar"

/**
 * A popup panel anchored to the element it is placed inside.
 *
 * For content that is not a menu of actions: a menu of actions is AppMenu
 * and stays data, so `q-list`/`q-item` never leak onto a screen. Whatever
 * lands here is custom markup the kit cannot name, which is why it arrives
 * in a slot.
 */
withDefaults(
  defineProps<{
    anchor?: QMenuProps["anchor"]
    self?: QMenuProps["self"]
    /**
     * Opened without taking the focus. For a list under a field that is still
     * being typed into: a menu that took the focus on opening took the next
     * key with it.
     */
    noFocus?: boolean
    /** Closed without handing the focus back to whatever had it before. */
    noRefocus?: boolean
    /**
     * Opened and closed by its model alone. Without it a press on what it is
     * anchored to toggles it, and a press in a field would close the list of
     * that field.
     */
    noParentEvent?: boolean
    /** At least as wide as what it is anchored to. */
    fit?: boolean
    maxHeight?: string
    maxWidth?: string
  }>(),
  {
    anchor: "bottom left",
    self: "top left",
    noFocus: false,
    noRefocus: false,
    noParentEvent: false,
    fit: false,
    maxHeight: undefined,
    maxWidth: undefined,
  }
)

const open = defineModel<boolean>({ default: false })

/**
 * Placed again whenever what is in it changes size.
 *
 * Trap: Quasar places a menu on the tick it opens and once more after its
 * transition, and skips a measurement of no height. Content that is still
 * being laid out then — the result of a connection check — was never placed
 * at all and stood at the foot of the screen, or grew down over the control
 * it is anchored above.
 */
const menu = useTemplateRef<{ updatePosition: () => void }>("menu")
const content = useTemplateRef<HTMLElement>("content")
let observer: ResizeObserver | null = null

function follow() {
  observer?.disconnect()
  if (content.value === null || typeof ResizeObserver === "undefined") return
  observer = new ResizeObserver(() => menu.value?.updatePosition())
  observer.observe(content.value)
}

function stop() {
  observer?.disconnect()
  observer = null
}

onBeforeUnmount(stop)
</script>

<template>
  <q-menu
    ref="menu"
    v-model="open"
    :anchor="anchor"
    :self="self"
    :no-focus="noFocus"
    :no-refocus="noRefocus"
    :no-parent-event="noParentEvent"
    :fit="fit"
    :max-height="maxHeight"
    :max-width="maxWidth"
    @before-show="follow"
    @show="follow"
    @hide="stop"
  >
    <div ref="content">
      <slot />
    </div>
  </q-menu>
</template>
