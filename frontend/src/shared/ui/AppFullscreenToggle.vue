<script setup lang="ts">
import { computed } from "vue"

import { t } from "@/shared/i18n"

import AppIconButton from "./AppIconButton.vue"
import { appIcons } from "./icons"
import { useFullscreen } from "./fullscreen"

/**
 * Fill the screen, or stop filling it, as one button — what F11 does, where a
 * pointer can reach it.
 *
 * Shaped like the theme toggle: the icon is what pressing it would give, and
 * the tooltip says the same in words. In the kit because it has a look (D11).
 */
const { active, supported, toggle } = useFullscreen()

const look = computed(() =>
  active.value
    ? { icon: appIcons.exitFullscreen, tooltip: t("kit.fullscreen.leave") }
    : { icon: appIcons.enterFullscreen, tooltip: t("kit.fullscreen.enter") }
)
</script>

<template>
  <AppIconButton
    :icon="look.icon"
    :tooltip="supported ? look.tooltip : t('kit.fullscreen.unsupported')"
    :disable="!supported"
    data-testid="fullscreen-toggle"
    :data-fullscreen="active ? 'on' : 'off'"
    @click="toggle()"
  />
</template>
