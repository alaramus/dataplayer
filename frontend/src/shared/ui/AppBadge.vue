<script setup lang="ts">
import { computed } from "vue"

import { badgeColor } from "./tokens"
import type { Tone } from "./tokens"

const props = withDefaults(defineProps<{ label: string; tone?: Tone }>(), { tone: "info" })

const color = computed(() => badgeColor(props.tone))
</script>

<template>
  <q-badge
    :color="color"
    :label="label"
  />
</template>
