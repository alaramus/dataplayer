<script setup lang="ts">
import type { QMenuProps } from "quasar"

/**
 * A popup panel anchored to the element it is placed inside.
 *
 * For content that is not a menu of actions: a menu of actions is AppMenu
 * and stays data, so `q-list`/`q-item` never leak onto a screen. Whatever
 * lands here is custom markup the kit cannot name, which is why it arrives
 * in a slot.
 */
withDefaults(defineProps<{ anchor?: QMenuProps["anchor"]; self?: QMenuProps["self"] }>(), {
  anchor: "bottom left",
  self: "top left",
})

const open = defineModel<boolean>({ default: false })
</script>

<template>
  <q-menu
    v-model="open"
    :anchor="anchor"
    :self="self"
  >
    <slot />
  </q-menu>
</template>
