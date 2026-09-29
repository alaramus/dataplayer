<script setup lang="ts">
import { computed, inject } from "vue"

import { formLayoutKey } from "./formLayout"

import { bannerLook } from "./tokens"
import type { Tone } from "./tokens"

const props = defineProps<{
  /** What the message is. The colour and the icon follow from it. */
  tone: Tone
}>()

const formLayout = inject(formLayoutKey, false)
const look = computed(() => bannerLook(props.tone, formLayout))
</script>

<template>
  <q-banner
    dense
    inline-actions
    class="app-banner"
    :class="[look.classes, { 'app-banner--form': formLayout }]"
  >
    <template #avatar>
      <q-icon
        :name="look.icon"
        :class="look.iconClasses"
      />
    </template>
    <slot />
    <!-- The one thing to do about what the banner says, at the end of its
         line rather than on a line of its own. -->
    <template
      v-if="$slots.action"
      #action
    >
      <slot name="action" />
    </template>
  </q-banner>
</template>

<style scoped>
/* The scale's body text and a control's icon (D185). A dense QBanner writes
   its message in Quasar's body2 — 14px, spaced out by .25px — beside a 28px
   icon, the one message in a window a size larger than everything round it. */
.app-banner {
  border-radius: var(--dp-radius-control);
}
.app-banner :deep(.q-banner__content) {
  font-size: var(--dp-font-size);
  line-height: var(--dp-line-height);
  letter-spacing: normal;
}
.app-banner :deep(.q-banner__avatar) {
  align-self: flex-start;
  min-width: 0;
}
.app-banner :deep(.q-banner__avatar > .q-icon) {
  font-size: var(--dp-icon-md);
}
.app-banner--form {
  min-height: 0;
  padding: 0;
  background: transparent;
  overflow-wrap: anywhere;
}
</style>
