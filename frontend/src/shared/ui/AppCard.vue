<script setup lang="ts">
import { computed } from "vue"

import AppSection from "./AppSection.vue"
import { panelStyle } from "./tokens"
import type { PanelSize } from "./tokens"

const props = withDefaults(
  defineProps<{
    title?: string
    size?: PanelSize
  }>(),
  { title: undefined, size: "sm" }
)

const style = computed(() => panelStyle(props.size))
</script>

<template>
  <q-card :style="{ width: style.width, maxWidth: style.maxWidth }">
    <AppSection v-if="title">
      <h2 class="dp-page-title">
        {{ title }}
      </h2>
    </AppSection>
    <slot />
  </q-card>
</template>
