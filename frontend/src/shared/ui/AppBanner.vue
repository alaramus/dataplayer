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
    :class="[look.classes, { 'app-banner--form': formLayout }]"
  >
    <template #avatar>
      <q-icon :name="look.icon" />
    </template>
    <slot />
    <!-- The one thing to do about what the banner says, at its end. -->
    <template
      v-if="$slots.action"
      #action
    >
      <slot name="action" />
    </template>
  </q-banner>
</template>

<style scoped>
.app-banner--form {
  min-height: 0;
  padding: 0;
  background: transparent;
  overflow-wrap: anywhere;
}
</style>
