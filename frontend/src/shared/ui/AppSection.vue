<script setup lang="ts">
import { SCROLL_MAX_HEIGHT } from "./tokens"

const props = withDefaults(
  defineProps<{
    /** Draw a rule above the section, separating it from the one before. */
    divided?: boolean
    /** Let the section scroll instead of stretching the panel past the screen. */
    scroll?: boolean
    /** Space the children apart, for a stack of form fields. */
    gutter?: boolean
  }>(),
  { divided: false, scroll: false, gutter: false }
)

const style = props.scroll ? { maxHeight: SCROLL_MAX_HEIGHT, overflow: "auto" } : undefined

// The separator makes this a two-root component, and Vue cannot guess which
// root an attribute belongs to. It belongs to the section.
defineOptions({ inheritAttrs: false })
</script>

<template>
  <q-separator v-if="divided" />
  <q-card-section
    v-bind="$attrs"
    :class="{ 'q-gutter-md': gutter }"
    :style="style"
  >
    <slot />
  </q-card-section>
</template>
