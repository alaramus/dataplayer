<script setup lang="ts">
import { ref } from "vue"

import AppButton from "./AppButton.vue"
import AppTooltip from "./AppTooltip.vue"

withDefaults(defineProps<{ label: string; disable?: boolean }>(), { disable: false })
const color = defineModel<string | null>({ default: null })
const open = ref(false)

function clear() {
  color.value = null
  open.value = false
}
</script>

<template>
  <q-btn
    flat
    dense
    round
    :disable="disable"
    :aria-label="label"
    aria-haspopup="dialog"
    :aria-expanded="open"
  >
    <span
      class="app-color-picker__swatch"
      :style="{ backgroundColor: color ?? undefined }"
    >
      <img
        src="/icons/rainbow.svg"
        alt=""
        width="24"
        height="24"
      >
    </span>
    <AppTooltip>{{ label }}</AppTooltip>
    <q-menu
      v-model="open"
      :disable="disable"
      role="dialog"
      :aria-label="label"
      anchor="bottom right"
      self="top right"
    >
      <q-color
        v-model="color"
        format-model="hex"
        flat
      />
      <AppButton
        class="app-color-picker__clear"
        variant="quiet"
        label="Reset color"
        :disable="color === null"
        @click="clear"
      />
    </q-menu>
  </q-btn>
</template>

<style scoped>
.app-color-picker__swatch {
  display: flex;
  width: 24px;
  height: 24px;
  border-radius: 50%;
}
.app-color-picker__clear {
  width: 100%;
}
</style>
