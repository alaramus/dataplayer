<script setup lang="ts">
import { AppIconButton, appIcons } from "@/shared/ui"
import { t } from "@/shared/i18n"

import { openQuickChat } from "./quickChatLauncher"
</script>

<template>
  <AppIconButton
    :icon="appIcons.quickChat"
    :tooltip="t('ai.quick.open')"
    data-testid="quick-chat-rail"
    @click="openQuickChat()"
  />
</template>
