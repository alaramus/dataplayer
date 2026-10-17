<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

// Imported by file rather than through the kit's barrel: `AppLayout` draws
// this, and the barrel holds `AppLayout`, so going through it is a cycle.
import AppButton from "@/shared/ui/AppButton.vue"
import AppIconButton from "@/shared/ui/AppIconButton.vue"
import { bannerLook, toneText } from "@/shared/ui/tokens"
import { t } from "@/shared/i18n"
import { notices } from "./notices"

/**
 * What the application has just said, while the activity sheet is shut (D114).
 *
 * Bottom right, above the button that owns the list, so a card that fades has
 * an obvious place it went to. Drawn over dialogs on purpose — see the layer
 * it uses.
 */
const props = defineProps<{
  /** Room taken by the application footer, so a card sits above it. */
  bottom?: number
}>()

const store = notices()
const offset = computed(() => `${(props.bottom ?? 0) + 12}px`)
</script>

<template>
  <div
    class="toasts"
    :style="{ bottom: offset }"
    role="log"
    aria-live="polite"
    aria-relevant="additions"
    data-testid="toasts"
  >
    <TransitionGroup name="toast">
      <div
        v-if="store.hidden.value > 0"
        key="hidden"
        class="toasts__more"
      >
        {{ t('notifications.toasts.more', { n: store.hidden.value }) }}
      </div>
      <article
        v-for="notice in store.cards.value"
        :key="notice.id"
        class="toasts__card"
        data-testid="toast"
      >
        <q-icon
          :name="bannerLook(notice.tone).icon"
          :class="toneText(notice.tone)"
          size="var(--dp-icon-sm)"
        />
        <p class="toasts__message">
          <strong
            v-if="notice.title"
            class="toasts__title"
          >{{ notice.title }}</strong>
          {{ notice.message }}
        </p>
        <AppButton
          v-if="notice.action"
          variant="secondary"
          size="sm"
          :label="notice.action.label"
          @click="notice.action.run(); store.dismiss(notice.id)"
        />
        <AppIconButton
          :icon="appIcons.close"
          :tooltip="t('notifications.toasts.dismiss')"
          compact
          @click="store.dismiss(notice.id)"
        />
      </article>
    </TransitionGroup>
  </div>
</template>

<style scoped>
/* Over the windows that raise most of the messages, and over everything else
   as well — see the layer's own note. */
.toasts {
  position: fixed;
  right: var(--dp-space-3);
  z-index: var(--dp-layer-toast);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--dp-space-2);
  width: 340px;
  max-width: calc(100vw - 2 * var(--dp-space-3));
  pointer-events: none;
}

.toasts__card {
  display: flex;
  align-items: flex-start;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-2) var(--dp-space-2) var(--dp-space-3);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  background: var(--dp-surface-raised);
  box-shadow: 0 6px 20px var(--dp-shadow-soft);
  pointer-events: auto;
}

/* What it is about, above what it says: a job's name. */
.toasts__title {
  display: block;
}
.toasts__message {
  flex: 1;
  min-width: 0;
  margin: 0;
  padding-top: 1px;
  overflow-wrap: anywhere;
  color: var(--dp-text);
}

.toasts__more {
  align-self: flex-end;
  padding: var(--dp-space-half) var(--dp-space-2);
  border-radius: var(--dp-radius-control);
  background: var(--dp-surface-raised);
  border: 1px solid var(--dp-border);
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
  pointer-events: auto;
}

.toast-enter-active, .toast-leave-active { transition: opacity 0.15s, transform 0.15s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(8px); }
.toast-leave-active { position: absolute; right: 0; }

@media (prefers-reduced-motion: reduce) {
  .toast-enter-active, .toast-leave-active { transition: none; }
}
</style>
