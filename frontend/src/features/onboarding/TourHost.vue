<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from "vue"

import { t } from "@/shared/i18n"
import { AppButton, useConfirm } from "@/shared/ui"

import { useTourDone } from "./done"
import { placeHint } from "./placement"
import type { Box, Size } from "./placement"
import {
  checkShown,
  currentChapter,
  endTour,
  offerMutation,
  tourFinished,
  tourState,
} from "./runner"
import { furthestTarget } from "./tour"

/**
 * The running tour, drawn over the workspace (D355): a dim with a hole, a
 * ring around the control the chapter is at, and a hint beside it.
 *
 * Rectangles are read every frame rather than observed, because what moves a
 * control — a window dragged, a panel resized, a list scrolled — has no one
 * event to listen to. The dim takes no clicks: the person works the real
 * screen through it.
 */

/** The first match that is laid out. Off screen is allowed: it is scrolled to. */
function find(selector: string): Element | null {
  for (const element of document.querySelectorAll(selector)) {
    const box = element.getBoundingClientRect()
    if (box.width > 0 && box.height > 0) return element
  }
  return null
}

/** Room between a control and its ring, so the ring does not cover its edge. */
const RING_GAP = 4

const ring = ref<Box | null>(null)
const targetIndex = ref(-1)
const viewport = ref<Size>({ width: window.innerWidth, height: window.innerHeight })
const cardSize = ref<Size>({ width: 0, height: 0 })
const card = useTemplateRef<HTMLElement>("card")

function differs(a: Box | null, b: Box | null): boolean {
  if (a === null || b === null) return a !== b
  return (
    Math.abs(a.top - b.top) > 0.5 ||
    Math.abs(a.left - b.left) > 0.5 ||
    Math.abs(a.width - b.width) > 0.5 ||
    Math.abs(a.height - b.height) > 0.5
  )
}

let lastElement: Element | null = null

function frame() {
  checkShown(find)
  const chapter = currentChapter.value
  let next: Box | null = null
  let index = -1
  if (chapter !== null) {
    index = furthestTarget(chapter, tourState.memory, find)
    const selector = index >= 0 ? chapter.targets[index]?.locate(tourState.memory) : null
    const element = selector ? find(selector) : null
    if (element !== null) {
      if (element !== lastElement) element.scrollIntoView({ block: "nearest", inline: "nearest" })
      const box = element.getBoundingClientRect()
      next = {
        top: box.top - RING_GAP,
        left: box.left - RING_GAP,
        width: box.width + RING_GAP * 2,
        height: box.height + RING_GAP * 2,
      }
    }
    lastElement = element
  }
  if (differs(ring.value, next)) ring.value = next
  targetIndex.value = index
  if (viewport.value.width !== window.innerWidth || viewport.value.height !== window.innerHeight) {
    viewport.value = { width: window.innerWidth, height: window.innerHeight }
  }
  const shown = card.value
  if (shown !== null && (shown.offsetWidth !== cardSize.value.width || shown.offsetHeight !== cardSize.value.height)) {
    cardSize.value = { width: shown.offsetWidth, height: shown.offsetHeight }
  }
}

let handle = 0
function loop() {
  frame()
  handle = requestAnimationFrame(loop)
}

watch(
  () => tourState.running,
  (running) => {
    cancelAnimationFrame(handle)
    lastElement = null
    ring.value = null
    if (running) loop()
  },
  { immediate: true }
)

// Completion is read off the mutation cache, so no feature imports the tour.
const queryClient = useQueryClient()
let unsubscribe = () => {}
onMounted(() => {
  unsubscribe = queryClient.getMutationCache().subscribe((event) => {
    if (event.type !== "updated" || event.action.type !== "success") return
    offerMutation({
      key: event.mutation.options.mutationKey,
      variables: event.mutation.state.variables,
      data: event.mutation.state.data,
    })
  })
})
onBeforeUnmount(() => {
  unsubscribe()
  cancelAnimationFrame(handle)
})

const position = computed(() =>
  t("onboarding.position", { n: tourState.chapter + 1, total: tourState.chapters.length })
)
const title = computed(() => (tourFinished.value ? t("onboarding.tour.finished.title") : (currentChapter.value?.title() ?? "")))

/** With nothing to ring, the chapter's first step says where to begin. */
const hint = computed(() => {
  if (tourFinished.value) return t("onboarding.tour.finished.text")
  const chapter = currentChapter.value
  if (chapter === null) return ""
  const target = chapter.targets[Math.max(targetIndex.value, 0)]
  return target?.hint(tourState.memory) ?? ""
})

const cardPlace = computed(() => {
  const size = cardSize.value
  if (tourFinished.value) {
    return {
      top: Math.max(0, (viewport.value.height - size.height) / 2),
      left: Math.max(0, (viewport.value.width - size.width) / 2),
    }
  }
  return placeHint(ring.value, size, viewport.value)
})

const ringStyle = computed(() => {
  const box = ring.value
  if (box === null) return {}
  return { top: `${box.top}px`, left: `${box.left}px`, width: `${box.width}px`, height: `${box.height}px` }
})

const cardStyle = computed(() => ({ top: `${cardPlace.value.top}px`, left: `${cardPlace.value.left}px` }))

const confirm = useConfirm()
const { markDone } = useTourDone()

async function stop() {
  const close = await confirm({
    title: t("onboarding.close_title"),
    message: t("onboarding.close_message"),
    confirmLabel: t("onboarding.close_confirm"),
    cancelLabel: t("onboarding.keep_going"),
  })
  if (!close) return
  void markDone()
  endTour()
}

function finish() {
  void markDone()
  endTour()
}
</script>

<template>
  <Teleport to="body">
    <template v-if="tourState.running">
      <div
        v-if="ring"
        class="tour-ring"
        :style="ringStyle"
        data-testid="tour-ring"
      />
      <div
        v-else-if="tourFinished"
        class="tour-dim"
      />
      <section
        ref="card"
        class="tour-card"
        :style="cardStyle"
        role="dialog"
        aria-live="polite"
        :aria-label="title"
        data-testid="tour-hint"
      >
        <header class="tour-card__head">
          <span
            v-if="!tourFinished"
            class="tour-card__position"
            data-testid="tour-position"
          >{{ position }}</span>
          <span
            class="tour-card__title"
            data-testid="tour-title"
          >{{ title }}</span>
        </header>
        <p
          class="tour-card__text"
          data-testid="tour-text"
        >
          {{ hint }}
        </p>
        <div class="tour-card__actions">
          <AppButton
            v-if="!tourFinished"
            variant="quiet"
            :label="t('onboarding.end_tour')"
            data-testid="tour-end"
            @click="stop"
          />
          <AppButton
            v-else
            :label="t('onboarding.finish')"
            data-testid="tour-finish"
            @click="finish"
          />
        </div>
      </section>
    </template>
  </Teleport>
</template>

<style scoped>
/* The hole is the ring itself: a shadow spread past every edge of the window
   dims everything but the box it surrounds. */
.tour-ring {
  position: fixed;
  z-index: var(--dp-layer-tour);
  border-radius: var(--dp-radius-panel);
  outline: 2px solid var(--dp-accent);
  box-shadow: 0 0 0 100vmax var(--dp-shadow-strong);
  pointer-events: none;
  transition: top 0.15s ease, left 0.15s ease, width 0.15s ease, height 0.15s ease;
}
.tour-dim {
  position: fixed;
  inset: 0;
  z-index: var(--dp-layer-tour);
  background: var(--dp-shadow-strong);
}
.tour-card {
  position: fixed;
  z-index: var(--dp-layer-tour);
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  width: var(--dp-width-popover);
  padding: var(--dp-space-3) var(--dp-space-4);
  border: 1px solid var(--dp-border-strong);
  border-radius: var(--dp-radius-panel);
  background: var(--dp-surface-raised);
  color: var(--dp-text);
  box-shadow: 0 2px 8px var(--dp-shadow);
  transition: top 0.15s ease, left 0.15s ease;
}
.tour-card__head {
  display: flex;
  align-items: baseline;
  gap: var(--dp-space-2);
  min-width: 0;
}
.tour-card__position {
  flex: none;
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
  color: var(--dp-text-muted);
}
.tour-card__title {
  font-weight: 500;
  font-size: var(--dp-font-size-lg);
}
.tour-card__text {
  margin: 0;
  font-size: var(--dp-font-size);
  line-height: var(--dp-line-height);
}
.tour-card__actions {
  display: flex;
  justify-content: flex-end;
}
</style>
