<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { usePreferences, useUpdatePreferences } from "@/features/preferences/api"
import { useLanguageChoice } from "@/features/preferences/languageChoice"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppButton, AppForm, AppRadioGroup, useConfirm, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"
import { THEME_CHOICES, useThemeStore } from "@/stores/theme"
import type { ThemeMode } from "@/stores/theme"

import { ONBOARDING_STEPS } from "./onboarding"

/**
 * The first-visit welcome: the language and a theme, then a short video tour.
 *
 * A window of its own rather than a page: it opens over the workspace the
 * person has just arrived at and goes away whole. Finishing or skipping
 * records the tour as done, so later visits open straight into the work.
 */
type Phase = "theme" | "tour"

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    /**
     * Where the welcome starts. The workspace starts at the theme choice;
     * replaying it from Preferences starts at the tour itself.
     */
    startPhase?: Phase
  }>(),
  { startPhase: "theme" }
)

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()

const theme = useThemeStore()
const language = useLanguageChoice()

const phase = ref<Phase>(props.startPhase)
const stepIndex = ref(0)

const step = computed(() => ONBOARDING_STEPS[stepIndex.value] ?? ONBOARDING_STEPS[0])
const isFirstStep = computed(() => stepIndex.value === 0)
const isLastStep = computed(() => stepIndex.value === ONBOARDING_STEPS.length - 1)
const position = computed(() =>
  t("onboarding.position", { n: stepIndex.value + 1, total: ONBOARDING_STEPS.length })
)
const primaryLabel = computed(() =>
  phase.value === "theme"
    ? t("onboarding.start")
    : isLastStep.value
      ? t("onboarding.finish")
      : t("onboarding.next")
)

function reset() {
  phase.value = props.startPhase
  stepIndex.value = 0
}

const preferences = usePreferences()
const savePreferences = useUpdatePreferences()
const toast = useToast()
const tourDone = computed(() => preferences.data.value?.welcome_tour_done === true)

/** Kept on the account, so no other browser of this person opens it again. */
async function markDone() {
  if (tourDone.value) return
  try {
    await savePreferences.mutateAsync({ welcome_tour_done: true })
  } catch (cause) {
    toast.error(messageOf(cause, t("onboarding.mark_failed")))
  }
}

/** Done, whether watched to the end or skipped halfway: never show again. */
function finish() {
  void markDone()
  emit("update:modelValue", false)
}

// Whatever closed it — a button, the frame's cross — the next opening
// starts over rather than mid-sentence.
watch(
  () => props.modelValue,
  (open) => {
    if (!open) reset()
  }
)

const confirm = useConfirm()

/**
 * The cross counts as skipping: ask first, and say where the tour is kept.
 * Replaying it from Preferences, it is already done — nothing to ask.
 */
async function confirmClose(): Promise<boolean> {
  if (tourDone.value) return true
  const close = await confirm({
    title: t("onboarding.close_title"),
    message: t("onboarding.close_message"),
    confirmLabel: t("onboarding.close_confirm"),
    cancelLabel: t("onboarding.keep_watching"),
  })
  if (close) void markDone()
  return close
}

function primary() {
  if (phase.value === "theme") phase.value = "tour"
  else if (isLastStep.value) finish()
  else stepIndex.value += 1
}

function back() {
  if (phase.value === "tour" && isFirstStep.value) phase.value = "theme"
  else stepIndex.value -= 1
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
    <div
      v-if="phase === 'theme'"
      class="onboarding"
    >
      <p class="onboarding__intro">
        {{ t('onboarding.intro') }}
      </p>
      <q-separator />
      <AppForm
        layout="section"
        labels="above"
      >
        <!-- Before the theme: everything after it is read in this language.
             Shown once the account has been read, so it never offers a guess. -->
        <AppRadioGroup
          v-if="language.chosen.value !== undefined"
          :model-value="language.chosen.value"
          :options="language.options.value"
          :label="t('language.label')"
          data-testid="onboarding-language"
          @update:model-value="language.choose"
        />
        <AppRadioGroup
          :model-value="theme.mode"
          :label="t('theme.label')"
          :options="THEME_CHOICES"
          data-testid="onboarding-theme"
          @update:model-value="chooseTheme"
        />
      </AppForm>
    </div>

    <!-- `step` guards the indexing: the index only ever names a shown step,
         but the type cannot know that (noUncheckedIndexedAccess). -->
    <div
      v-else-if="step"
      class="onboarding"
    >
      <div class="onboarding__head">
        <span
          class="onboarding__position"
          data-testid="onboarding-position"
        >{{ position }}</span>
        <span class="onboarding__title">{{ step.title }}</span>
      </div>
      <!-- :key restarts the player when the step changes: without it the
           previous clip keeps its last frame under the new title. -->
      <video
        :key="step.id"
        class="onboarding__video"
        :src="step.src"
        controls
        preload="metadata"
        playsinline
        data-testid="onboarding-video"
      />
    </div>

    <template #actions>
      <AppButton
        variant="quiet"
        :label="phase === 'theme' ? t('onboarding.skip_tour') : t('onboarding.skip')"
        data-testid="onboarding-skip"
        @click="finish"
      />
      <AppButton
        v-if="phase === 'tour'"
        variant="quiet"
        :label="t('catalog.common.back')"
        data-testid="onboarding-back"
        @click="back"
      />
      <AppButton
        :label="primaryLabel"
        data-testid="onboarding-primary"
        @click="primary"
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
/* The one sentence the welcome is about: full size, in the primary text. */
/* The window's subtitle, set as every window's is: at 15px it stood heavier
   than the title above it. */
.onboarding__intro {
  margin: 0;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size);
  line-height: var(--dp-line-height);
}
.onboarding__head {
  display: flex;
  align-items: baseline;
  gap: var(--dp-space-3);
  min-width: 0;
}
.onboarding__position {
  flex: none;
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
  color: var(--dp-text-muted);
}
.onboarding__title {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* A dark ground behind the clip, so a narrow recording stands on something
   deliberate rather than on the window's surface while it loads. */
.onboarding__video {
  flex: 1;
  width: 100%;
  max-height: 100%;
  min-height: 0;
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  background: var(--dp-chrome);
}
</style>
