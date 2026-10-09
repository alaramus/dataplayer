<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { AppIconButton, AppPopup } from "@/shared/ui"

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
        <strong>Choose a model</strong>
        <AppIconButton
          :icon="appIcons.close"
          tooltip="Close"
          compact
          data-testid="ai-model-hint-close"
          @click="open = false"
        />
      </div>
      <p>To start chatting, choose a model in this Model list. Each provider needs its own API key — open a model in the list and choose the key icon to set it.</p>
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
