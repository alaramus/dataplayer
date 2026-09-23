<script setup lang="ts">
import { computed } from "vue"

import { useThemeStore } from "@/stores/theme"

import AppIconButton from "./AppIconButton.vue"
import { appIcons } from "./icons"

/**
 * Light or dark, as one button. The icon is what pressing it would give, not
 * what is showing, and the tooltip says the same in words. Pressing it
 * chooses that theme outright, so it stops following the system; the
 * three-way choice is in Preferences.
 *
 * In the kit because it has a look (D11). The store behind it is the only
 * place that knows Quasar has a Dark plugin.
 */
const theme = useThemeStore()

const look = computed(() =>
  theme.dark
    ? { icon: appIcons.lightTheme, tooltip: "Switch to the light theme" }
    : { icon: appIcons.darkTheme, tooltip: "Switch to the dark theme" }
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
