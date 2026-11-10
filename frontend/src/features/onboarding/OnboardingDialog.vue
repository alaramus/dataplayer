<script setup lang="ts">
import { useLanguageChoice } from "@/features/preferences/languageChoice"
import { t } from "@/shared/i18n"
import { AppButton, AppForm, AppRadioGroup, AppSelect, useConfirm } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"
import { THEME_CHOICES, useThemeStore } from "@/stores/theme"
import type { ThemeMode } from "@/stores/theme"

import { useTourDone } from "./done"
import { BASICS_TOUR } from "./basics"
import { startTour } from "./runner"

/**
 * The first-visit welcome: the language and a theme, then the tour or not.
 *
 * A window of its own rather than a page: it opens over the workspace the
 * person has just arrived at and goes away whole. The tour itself runs over
 * the workspace (D355), so taking it closes this window; turning it down
 * records the welcome as done, so later visits open straight into the work.
 */
const props = defineProps<{ modelValue: boolean }>()

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()

const theme = useThemeStore()
const language = useLanguageChoice()
const { done, markDone } = useTourDone()

/** Done once the tour ends or is ended, not now: a reload brings the welcome back. */
function takeTour() {
  emit("update:modelValue", false)
  startTour(BASICS_TOUR)
}

function lookAround() {
  void markDone()
  emit("update:modelValue", false)
}

const confirm = useConfirm()

/** The cross counts as turning the tour down: ask first, and say where it is kept. */
async function confirmClose(): Promise<boolean> {
  if (done.value) return true
  const close = await confirm({
    title: t("onboarding.close_title"),
    message: t("onboarding.close_message"),
    confirmLabel: t("onboarding.close_confirm"),
    cancelLabel: t("onboarding.keep_going"),
  })
  if (close) void markDone()
  return close
}

function chooseTheme(value: string) {
  theme.set(value as ThemeMode)
}
</script>

<template>
  <WindowDialog
    :model-value="props.modelValue"
    :title="t('onboarding.title')"
    size="wide-form"
    sizing="stable"
    :before-close="confirmClose"
    data-testid="onboarding-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="onboarding">
      <p class="onboarding__intro">
        {{ t('onboarding.intro') }}
      </p>
      <q-separator />
      <!-- Both lists grow — more languages, more themes — so neither may cost
           a line per entry: the language is a choice in one row, the themes a
           grid. Choosing a theme repaints the whole application, which is
           its preview. -->
      <AppForm layout="section">
        <!-- Before the theme: everything after it is read in this language.
             Shown once the account has been read, so it never offers a guess. -->
        <AppSelect
          v-if="language.chosen.value !== undefined"
          :model-value="language.chosen.value"
          :options="language.options.value"
          :label="t('language.label')"
          class="onboarding__language"
          data-testid="onboarding-language"
          @update:model-value="language.choose"
        />
        <AppRadioGroup
          :model-value="theme.mode"
          :label="t('theme.label')"
          :options="THEME_CHOICES"
          grid
          data-testid="onboarding-theme"
          @update:model-value="chooseTheme"
        />
      </AppForm>
      <p class="onboarding__intro">
        {{ t('onboarding.tour_offer') }}
      </p>
    </div>

    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('onboarding.look_around')"
        data-testid="onboarding-skip"
        @click="lookAround"
      />
      <AppButton
        :label="t('onboarding.take_tour')"
        data-testid="onboarding-primary"
        @click="takeTour"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.onboarding {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-3);
  padding: var(--dp-space-4);
  min-height: 0;
}
/* The window's subtitle, set as every window's is: at 15px it stood heavier
   than the title above it. */
.onboarding__intro {
  margin: 0;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size);
  line-height: var(--dp-line-height);
}
.onboarding__language {
  max-width: var(--dp-width-popover);
}
</style>
