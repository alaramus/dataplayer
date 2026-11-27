<script setup lang="ts">
import { computed, nextTick, ref, useTemplateRef, watch } from "vue"

import ProseBlock from "@/features/content/markdown/ProseBlock.vue"
import { outlineProse, renderProse } from "@/features/content/markdown/render"
import { useProviderHits } from "@/features/search/useProviderHits"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppBanner,
  AppEmptyState,
  AppIconButton,
  AppInput,
  AppSpinner,
  appIcons,
  useToast,
} from "@/shared/ui"

import { useGuidePage, useGuidePages } from "./api"
import { foundPages, groupedContents } from "./contents"
import { pageOfLink } from "./links"
import { shownGuidePage } from "./state"

/**
 * The Help Center: the user's guide (D183) with its contents on the left —
 * every page under its section, the page being read opened onto its headings
 * — a search over every page, and Back.
 *
 * What a search finds is the search's own guide provider (D197), so the words
 * match here as they do in the header's field.
 */
const toast = useToast()
const pages = useGuidePages()
const page = useGuidePage(shownGuidePage)

const markdown = computed(() => page.data.value?.markdown ?? "")
const outline = computed(() => outlineProse([markdown.value]))
const html = computed(() =>
  markdown.value === "" ? "" : renderProse(markdown.value, { headingIds: outline.value.blockHeadingIds[0] ?? [] })
)
// The page's sections: its title is the page's own line in the contents.
const sections = computed(() => outline.value.headings.filter((heading) => heading.level === 2))

const groups = computed(() => groupedContents(pages.data.value ?? []))

const query = ref("")
const { hits } = useProviderHits(query, "guide", "guide")
const found = computed(() => (hits.value === null ? null : foundPages(hits.value)))

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

function show(key: string) {
  if (key === shownGuidePage.value) body.value?.scrollTo({ top: 0 })
  else shownGuidePage.value = key
}

function scrollToSection(id: string) {
  const heading = body.value?.querySelector<HTMLElement>(`#${CSS.escape(id)}`)
  heading?.scrollIntoView({ block: "start" })
  heading?.focus({ preventScroll: true })
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
      <AppInput
        v-model="query"
        class="guide-window__search"
        clearable
        compact
        :prepend-icon="appIcons.search"
        :placeholder="t('onboarding.guide.search')"
        data-testid="guide-search"
      />
    </div>
    <div class="guide-window__main">
      <nav
        class="guide-window__contents"
        :aria-label="t('onboarding.guide.contents')"
        data-testid="guide-contents"
      >
        <template v-if="found !== null">
          <button
            v-for="one in found"
            :key="one.key"
            type="button"
            class="guide-window__entry guide-window__found"
            :class="{ 'guide-window__entry--current': one.key === shownGuidePage }"
            :aria-current="one.key === shownGuidePage ? 'page' : undefined"
            :data-testid="`guide-found-${one.key}`"
            @click="show(one.key)"
          >
            <span class="guide-window__found-title">{{ one.title }}</span>
            <span
              v-if="one.excerpt.length > 0"
              class="guide-window__excerpt"
            >
              <component
                :is="run.hit ? 'mark' : 'span'"
                v-for="(run, index) in one.excerpt"
                :key="index"
                :class="{ 'guide-window__hit': run.hit }"
              >{{ run.text }}</component>
            </span>
          </button>
          <AppEmptyState
            v-if="found.length === 0"
            icon="search_off"
            :text="t('onboarding.guide.nothing_found')"
            data-testid="guide-nothing-found"
          />
        </template>
        <template v-else>
          <section
            v-for="group in groups"
            :key="group.section"
            class="guide-window__group"
          >
            <div class="guide-window__section dp-overline">
              {{ t(`onboarding.guide.sections.${group.section}`) }}
            </div>
            <template
              v-for="one in group.pages"
              :key="one.key"
            >
              <button
                type="button"
                class="guide-window__entry"
                :class="{ 'guide-window__entry--current': one.key === shownGuidePage }"
                :aria-current="one.key === shownGuidePage ? 'page' : undefined"
                :data-testid="`guide-page-${one.key}`"
                @click="show(one.key)"
              >
                {{ one.title }}
              </button>
              <div
                v-if="one.key === shownGuidePage && sections.length > 0"
                class="guide-window__headings"
                :aria-label="t('onboarding.guide.on_this_page')"
                role="group"
              >
                <button
                  v-for="heading in sections"
                  :key="heading.id"
                  type="button"
                  class="guide-window__entry guide-window__heading"
                  :data-testid="`guide-heading-${heading.id}`"
                  @click="scrollToSection(heading.id)"
                >
                  {{ heading.title }}
                </button>
              </div>
            </template>
          </section>
        </template>
      </nav>
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
.guide-window__search {
  flex: 1;
  min-width: 0;
}
.guide-window__main {
  flex: 1;
  min-height: 0;
  display: flex;
}
.guide-window__contents {
  flex: 0 0 var(--dp-side-column-width);
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--dp-space-2);
  border-inline-end: 1px solid var(--dp-border-faint);
}
.guide-window__group + .guide-window__group {
  margin-top: var(--dp-space-3);
}
.guide-window__section {
  padding: var(--dp-space-1) var(--dp-space-2);
}
/* Drawn as a section of a settings page is: the page read is the current
   page of a list, marked as a tab is (D186). */
.guide-window__entry {
  display: block;
  width: 100%;
  padding: var(--dp-space-1) var(--dp-space-2);
  border: 0;
  border-radius: var(--dp-radius-control);
  background: transparent;
  color: var(--dp-text);
  font: inherit;
  text-align: start;
  cursor: pointer;
}
.guide-window__entry:hover {
  background: var(--dp-hover);
}
.guide-window__entry:focus-visible {
  outline: 1px solid var(--dp-focus-border);
}
.guide-window__entry--current {
  background: var(--dp-tab-current);
  font-weight: 500;
}
.guide-window__headings {
  margin: var(--dp-space-1) 0;
}
.guide-window__heading {
  padding-inline-start: calc(var(--dp-space-2) + var(--dp-space-3));
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
.guide-window__found + .guide-window__found {
  margin-top: var(--dp-space-1);
}
.guide-window__found-title {
  display: block;
}
.guide-window__excerpt {
  display: block;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
/* Marked as a found word is under the search field. */
.guide-window__hit {
  background: color-mix(in srgb, var(--dp-find) 45%, transparent);
  color: inherit;
}
.guide-window__body {
  flex: 1;
  min-width: 0;
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
