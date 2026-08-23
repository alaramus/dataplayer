<script setup lang="ts">
import { computed } from "vue"

import { useThemeStore } from "@/stores/theme"

import AppIconButton from "./AppIconButton.vue"

/**
 * Light or dark, as one button.
 *
 * The icon is what pressing it would give, not what is showing: a moon in the
 * light theme, a sun in the dark one. The tooltip says the same thing in
 * words, because an icon alone names nothing.
 *
 * In the kit rather than in a screen: it has a look, and by D11 anything with
 * a look is wrapped once here. The store behind it is the only place that
 * knows Quasar has a Dark plugin.
 */
const theme = useThemeStore()

const look = computed(() =>
  theme.dark
    ? { icon: "light_mode", tooltip: "Switch to the light theme" }
    : { icon: "dark_mode", tooltip: "Switch to the dark theme" }
)
</script>

<template>
  <AppIconButton
    :icon="look.icon"
    :tooltip="look.tooltip"
    data-testid="theme-toggle"
    :data-theme="theme.dark ? 'dark' : 'light'"
    @click="theme.toggle()"
  />
</template>
