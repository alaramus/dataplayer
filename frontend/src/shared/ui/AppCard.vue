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
  <!-- The one look of a card (frontend.md): a border and the panel corner,
       no shadow. Quasar's raised card was a second kind beside every
       AppCardFrame of the workspace. -->
  <q-card
    flat
    bordered
    class="app-card"
    :style="{ width: style.width, maxWidth: style.maxWidth }"
  >
    <AppSection v-if="title">
      <h2 class="dp-page-title">
        {{ title }}
      </h2>
    </AppSection>
    <slot />
  </q-card>
</template>

<style scoped>
.app-card {
  border-color: var(--dp-border);
  border-radius: var(--dp-radius-panel);
  background: var(--dp-surface);
}
</style>
