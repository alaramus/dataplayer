<script setup lang="ts">
import { t } from "@/shared/i18n"
import AppTaskbar from "@/shared/ui/AppTaskbar.vue"
import AppTaskbarItem from "@/shared/ui/AppTaskbarItem.vue"

import type { WorkspaceContext } from "./context"

/**
 * The sections that are off the screen, on the bar at the foot of it.
 *
 * Beside the windows and drawn as they are, because it is the same fact about
 * both: something is open and not in front of you. A column pushed aside used
 * to be forty pixels of empty strip in the row it came from — room spent on a
 * handle — and the bar is where this application already keeps what is not on
 * the screen (D69, D92).
 *
 * Placed by the feature rather than by the engine: where the bar is belongs to
 * the application, and the engine has no notion of a footer.
 */
defineProps<{ context: WorkspaceContext }>()
</script>

<template>
  <AppTaskbar
    v-if="context.aside.value.length"
    :label="t('layout.taskbar.label')"
    data-testid="workspace-taskbar"
  >
    <AppTaskbarItem
      v-for="section in context.aside.value"
      :key="section.id"
      :title="`${section.title} · ${section.panels}`"
      :icon="section.icon"
      aside
      :tooltip="t('layout.taskbar.bring_back', { title: section.title })"
      :data-testid="`workspace-aside-${section.id}`"
      @open="context.bringBack(section.id)"
    />
  </AppTaskbar>
</template>
