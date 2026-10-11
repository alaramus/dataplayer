<script setup lang="ts">
import { computed } from "vue"

import { t } from "@/shared/i18n"
import { useThemeStore } from "@/stores/theme"

import AppIconButton from "./AppIconButton.vue"
import { appIcons } from "./icons"

/**
 * Light or dark, as one button. The icon is what pressing it would give, not
 * what is showing, and the tooltip names it. Pressing it chooses that theme
 * outright, so it stops following the system: the last light or dark theme
 * chosen, Light or Dark when none was. The wider choice is in Preferences.
 *
 * In the kit because it has a look (D11). The store behind it is the only
 * place that knows Quasar has a Dark plugin.
 */
const theme = useThemeStore()

const look = computed(() => ({
  icon: theme.dark ? appIcons.lightTheme : appIcons.darkTheme,
  tooltip: t("theme.switch_to", { theme: theme.opposite.label }),
}))
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
