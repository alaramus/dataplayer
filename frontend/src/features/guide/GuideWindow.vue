<script setup lang="ts">
import { computed, nextTick, ref, useTemplateRef, watch } from "vue"

import ProseBlock from "@/features/content/markdown/ProseBlock.vue"
import { renderProse } from "@/features/content/markdown/render"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppBanner, AppIconButton, AppSelect, AppSpinner, appIcons, useToast } from "@/shared/ui"

import { useGuidePage, useGuidePages } from "./api"
import { pageOfLink } from "./links"
import { shownGuidePage } from "./state"

/**
 * One page of the user's guide (D183), and the way between its pages: the
 * links in the text, a list of every page, and Back.
 */
const toast = useToast()
const pages = useGuidePages()
const page = useGuidePage(shownGuidePage)
const html = computed(() => (page.data.value ? renderProse(page.data.value.markdown) : ""))
const options = computed(() =>
  (pages.data.value ?? []).map((one) => ({ label: one.title, value: one.key }))
)

// Every turn of the page is remembered, including one made by a Guide button
// elsewhere while the window is open, so Back leads to what was read before.
const history = ref<string[]>([])
let goingBack = false
const body = useTemplateRef<HTMLElement>("body")

watch(shownGuidePage, async (_next, previous) => {
  if (goingBack) goingBack = false
  else history.value.push(previous)
  await nextTick()
  body.value?.scrollTo({ top: 0 })
})

function back() {
  const previous = history.value.pop()
  if (previous === undefined) return
  goingBack = true
  shownGuidePage.value = previous
}

function choose(value: unknown) {
  if (typeof value === "string") shownGuidePage.value = value
}

function follow(event: MouseEvent) {
  const origin = event.target
  if (!(origin instanceof Element)) return
  const link = origin.closest<HTMLElement>("a[data-relative-link]")
  if (link === null) return
  event.preventDefault()
  const key = pageOfLink(link.dataset.relativeLink ?? "")
  if (key === null) {
    toast.info(t("onboarding.guide.not_a_page"))
    return
  }
  shownGuidePage.value = key
}
</script>

<template>
  <div
    class="guide-window"
    data-testid="guide-window"
  >
    <div class="guide-window__bar">
      <AppIconButton
        :icon="appIcons.arrowBack"
        :tooltip="t('catalog.common.back')"
        :disable="history.length === 0"
        data-testid="guide-back"
        @click="back"
      />
      <AppSelect
        class="guide-window__pages"
        :model-value="shownGuidePage"
        :options="options"
        compact
        data-testid="guide-pages"
        @update:model-value="choose"
      />
    </div>
    <div
      ref="body"
      class="guide-window__body"
      @click="follow"
    >
      <AppSpinner v-if="page.isPending.value" />
      <AppBanner
        v-else-if="page.isError.value"
        tone="error"
      >
        {{ messageOf(page.error.value, t('onboarding.guide.read_failed')) }}
      </AppBanner>
      <ProseBlock
        v-else
        class="guide-window__text"
        :html="html"
        data-testid="guide-text"
      />
    </div>
  </div>
</template>

<style scoped>
.guide-window {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.guide-window__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-1) var(--dp-space-3);
  border-bottom: 1px solid var(--dp-border);
}
.guide-window__pages {
  flex: 1;
  min-width: 0;
}
.guide-window__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--dp-space-2) var(--dp-space-5) var(--dp-space-5);
}
.guide-window__text {
  font-size: var(--dp-prose-font-size);
  line-height: var(--dp-prose-line-height);
}
</style>
