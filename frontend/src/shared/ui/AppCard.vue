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
      <div class="text-h6">
        {{ title }}
      </div>
    </AppSection>
    <slot />
  </q-card>
</template>
