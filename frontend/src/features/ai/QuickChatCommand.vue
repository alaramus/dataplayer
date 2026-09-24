<script setup lang="ts">
import { AppIconButton, appIcons } from "@/shared/ui"

import { openQuickChat } from "./quickChatLauncher"
</script>

<template>
  <AppIconButton
    :icon="appIcons.quickChat"
    tooltip="Quick chat"
    data-testid="quick-chat-rail"
    @click="openQuickChat()"
  />
</template>
