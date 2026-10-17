<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { AppIconButton, AppPopup } from "@/shared/ui"
import { t } from "@/shared/i18n"

/**
 * Where to choose a model when none is chosen yet.
 *
 * A small popup anchored to the Model field it names, opening above it: the
 * composers stand at the bottom of their surface, and a sheet along the edge
 * would talk about the field from across the screen. It closes with the
 * cross, with Escape, and with a click anywhere outside itself.
 */
const open = defineModel<boolean>({ default: false })
</script>

<template>
  <AppPopup
    v-model="open"
    anchor="top left"
    self="bottom left"
    no-parent-event
    no-focus
    no-refocus
    max-width="300px"
  >
    <div
      class="ai-model-hint"
      data-testid="ai-model-hint"
    >
      <div class="ai-model-hint__head">
        <strong>{{ t('ai.hint.title') }}</strong>
        <AppIconButton
          :icon="appIcons.close"
          :tooltip="t('catalog.common.close')"
          compact
          data-testid="ai-model-hint-close"
          @click="open = false"
        />
      </div>
      <p>{{ t('ai.hint.text') }}</p>
    </div>
  </AppPopup>
</template>

<style scoped>
.ai-model-hint {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  padding: var(--dp-space-2) var(--dp-space-2) var(--dp-space-2) var(--dp-space-3);
}

.ai-model-hint__head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}

.ai-model-hint__head > strong { flex: 1; }

.ai-model-hint p { margin: 0; }
</style>
