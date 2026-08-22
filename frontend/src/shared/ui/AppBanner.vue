<script setup lang="ts">
import { computed } from "vue"

import { bannerLook } from "./tokens"
import type { Tone } from "./tokens"

const props = defineProps<{
  /** What the message is. The colour and the icon follow from it. */
  tone: Tone
}>()

const look = computed(() => bannerLook(props.tone))
</script>

<template>
  <q-banner
    dense
    :class="look.classes"
  >
    <template #avatar>
      <q-icon :name="look.icon" />
    </template>
    <slot />
  </q-banner>
</template>
