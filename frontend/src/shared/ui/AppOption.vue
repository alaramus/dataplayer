<script setup lang="ts">
import { t } from "@/shared/i18n"

import AppButton from "./AppButton.vue"
import AppIconButton from "./AppIconButton.vue"
import type { SelectOption, TextRun } from "./AppSelect.vue"
import { appIcons } from "./icons"

/**
 * One row of a list of choices: a heading, or a choice with its icon, its
 * second line and an action of its own.
 *
 * Drawn the same way wherever choices are listed — under a select and under
 * a combobox — so the two cannot drift into two looks for one thing. What the
 * row does when pressed is its list's: the attributes and listeners it is
 * given land on the row itself.
 */
defineProps<{ option: SelectOption }>()

const emit = defineEmits<{
  action: [option: SelectOption]
  /** Its cross, or a heading's Clear: taken out of the list, not chosen. */
  remove: [option: SelectOption]
}>()

/** Text as it came, the matched runs marked. Never HTML (D50). */
function runsOf(runs: readonly TextRun[] | undefined, text: string): readonly TextRun[] {
  return runs !== undefined && runs.length > 0 ? runs : [{ text, hit: false }]
}
</script>

<template>
  <q-item
    v-if="option.group"
    :class="{ 'app-option--separator': option.separator }"
  >
    <q-item-section>
      <q-item-label header>
        {{ option.label }}
      </q-item-label>
      <q-item-label
        v-if="option.description"
        caption
      >
        {{ option.description }}
      </q-item-label>
    </q-item-section>
    <!-- A heading is never chosen, but its action stays a command: the click
         never reaches the row's own handler, which a heading does not have. -->
    <q-item-section
      v-if="option.actionIcon && option.actionLabel"
      side
      class="app-option__action"
    >
      <AppIconButton
        :icon="option.actionIcon"
        :tooltip="option.actionLabel"
        :active="option.actionActive"
        @click.stop.prevent="emit('action', option)"
      />
    </q-item-section>
    <!-- Trap: QBtn hands the focus to a helper of its own on mouseup unless
         the press was refused before it saw it, and the list stays open over
         a field that has to keep the focus. -->
    <q-item-section
      v-if="option.removeLabel"
      side
      class="app-option__action"
      @mousedown.capture.prevent
    >
      <AppButton
        variant="quiet"
        size="sm"
        :label="t('kit.option.clear')"
        :aria-label="option.removeLabel"
        @click.stop.prevent="emit('remove', option)"
      />
    </q-item-section>
  </q-item>
  <q-item
    v-else
    :class="{ 'app-option--warning': option.tone === 'warning', 'app-option--separator': option.separator }"
  >
    <q-item-section
      v-if="option.icon"
      avatar
    >
      <q-icon
        :name="option.icon"
        :color="option.actionActive ? 'positive' : undefined"
      />
    </q-item-section>
    <q-item-section class="app-option__text">
      <q-item-label class="app-option__line">
        <!-- One element a run, so no space is put between two of them. -->
        <component
          :is="run.hit ? 'mark' : 'span'"
          v-for="(run, index) in runsOf(option.labelRuns, option.label)"
          :key="index"
          :class="{ 'app-option__hit': run.hit }"
        >
          {{ run.text }}
        </component>
      </q-item-label>
      <q-item-label
        v-if="option.description || option.descriptionRuns?.length"
        caption
        class="app-option__line"
      >
        <component
          :is="run.hit ? 'mark' : 'span'"
          v-for="(run, index) in runsOf(option.descriptionRuns, option.description ?? '')"
          :key="index"
          :class="{ 'app-option__hit': run.hit }"
        >
          {{ run.text }}
        </component>
      </q-item-label>
    </q-item-section>
    <q-item-section
      v-if="option.actionIcon && option.actionLabel"
      side
      class="app-option__action"
    >
      <AppIconButton
        :icon="option.actionIcon"
        :tooltip="option.actionLabel"
        :active="option.actionActive"
        @click.stop.prevent="emit('action', option)"
      />
    </q-item-section>
    <q-item-section
      v-if="option.removeLabel"
      side
      class="app-option__action"
      @mousedown.capture.prevent
    >
      <AppIconButton
        :icon="appIcons.close"
        :tooltip="option.removeLabel"
        @click.stop.prevent="emit('remove', option)"
      />
    </q-item-section>
  </q-item>
</template>

<style scoped>
.app-option--warning { color: var(--dp-tone-warning-text); }
/* A line above the row, separating runs of choices. A hairline border in the
   theme's faint line colour, as elsewhere in the kit. */
.app-option--separator { border-top: 1px solid var(--dp-border-faint); }
/* The row may be unavailable while its button stays a command — a key window
   on a choice without a key. Quasar marks every descendant of a disabled row
   not-allowed with !important, so the rule names the descendants too: an
   inherited cursor loses to a directly applied one. The scoped attribute
   outweighs Quasar the way AppTooltip does. */
.app-option__action,
.app-option__action * { cursor: pointer !important; }
.app-option__text { min-width: 0; }
/* What matched, in the colour a find in a document is marked with. */
.app-option__hit {
  background: color-mix(in srgb, var(--dp-find) 45%, transparent);
  color: inherit;
}
</style>
