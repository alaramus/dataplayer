<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from "vue"
import { useRouter } from "vue-router"

import type { PreferenceSectionId } from "@/features/preferences/sections"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppButton, useConfirm, useToast } from "@/shared/ui"

import { useTourDone } from "./done"
import { tourKit } from "./kit"
import { placeHint } from "./placement"
import type { Box, Size } from "./placement"
import {
  checkShown,
  currentChapter,
  endTour,
  nextChapter,
  offerMutation,
  prepared,
  runningTour,
  tourFinished,
  tourState,
} from "./runner"
import { furthestTarget, offersNext } from "./tour"
import type { TourChapter } from "./tour"

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

function count(selector: string): number {
  let laidOut = 0
  for (const element of document.querySelectorAll(selector)) {
    const box = element.getBoundingClientRect()
    if (box.width > 0 && box.height > 0) laidOut += 1
  }
  return laidOut
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

// Above the loop, which starts while this component is still being set up.
const queryClient = useQueryClient()

/**
 * Whether what the chapter asks for has been asked and is not answered yet.
 * The window it was asked from closes first, and re-reading the page then
 * would ring an earlier step — the + of a database already being made.
 */
function answering(chapter: TourChapter): boolean {
  return chapter.done.kind === "mutation" && queryClient.isMutating({ mutationKey: [...chapter.done.key] }) > 0
}

function frame() {
  checkShown(find, count)
  const chapter = currentChapter.value
  let next: Box | null = null
  let index = -1
  if (chapter !== null && answering(chapter)) {
    // Held where it was until the answer moves the tour on.
    next = ring.value
    index = targetIndex.value
  } else if (chapter !== null) {
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

const running = computed(() => runningTour.value !== null)

watch(
  running,
  (now) => {
    cancelAnimationFrame(handle)
    lastElement = null
    ring.value = null
    if (now) loop()
  },
  { immediate: true }
)

// Completion is read off the mutation cache, so no feature imports the tour.
const kit = tourKit(queryClient)
const toast = useToast()

// What a short tour makes for itself, before its first chapter (D356).
watch(
  () => tourState.preparing,
  async (preparing) => {
    const tour = runningTour.value
    if (!preparing || tour?.setup === undefined) return
    try {
      prepared(await tour.setup(kit))
    } catch (cause) {
      toast.error(messageOf(cause, t("onboarding.tours.setup_failed")))
      endTour()
    }
  },
  { immediate: true }
)
/**
 * Capture phase, so the chapter completes before what the press opens can
 * hide the control and send the hint back to the chapter's first target.
 */
function pressed(event: MouseEvent) {
  const chapter = currentChapter.value
  if (chapter === null || lastElement === null || !(event.target instanceof Node)) return
  if (chapter.targets[targetIndex.value]?.pressCompletes !== true) return
  if (lastElement.contains(event.target)) nextChapter()
}

let unsubscribe = () => {}
onMounted(() => {
  document.addEventListener("click", pressed, true)
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
  document.removeEventListener("click", pressed, true)
  unsubscribe()
  cancelAnimationFrame(handle)
})

const position = computed(() =>
  t("onboarding.position", {
    n: tourState.chapter + 1,
    total: runningTour.value?.chapters.length ?? 0,
  })
)
const closing = computed(() => runningTour.value?.closing ?? null)
const title = computed(() => {
  if (tourState.preparing) return runningTour.value?.title() ?? ""
  if (tourFinished.value) return closing.value?.title() ?? ""
  return currentChapter.value?.title() ?? ""
})
const isLast = computed(
  () => tourState.chapter === (runningTour.value?.chapters.length ?? 0) - 1
)
const canNext = computed(() => {
  const chapter = currentChapter.value
  return chapter !== null && offersNext(chapter, targetIndex.value)
})
/** On a last chapter only shown, ending and finishing are the same: Finish alone. */
const finishOnly = computed(() => isLast.value && currentChapter.value?.done.kind === "next")
const offersMoreTours = computed(() => isLast.value && runningTour.value?.moreTours === true)

/** With nothing to ring, the chapter's first step says where to begin. */
const hint = computed(() => {
  if (tourState.preparing) return t("onboarding.tours.preparing")
  if (tourFinished.value) return closing.value?.text() ?? ""
  const chapter = currentChapter.value
  if (chapter === null) return ""
  const target = chapter.targets[Math.max(targetIndex.value, 0)]
  return target?.hint(tourState.memory) ?? ""
})

const cardPlace = computed(() => {
  const size = cardSize.value
  if (tourFinished.value || tourState.preparing) {
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

/** Done either way, and what the tour made for itself taken back. */
function close() {
  const tour = runningTour.value
  if (tour === null) return
  const memory = tourState.memory
  void markDone(tour.id)
  endTour()
  if (tour.cleanup !== undefined) {
    tour.cleanup(kit, memory).catch((cause: unknown) => {
      toast.error(messageOf(cause, t("onboarding.tours.cleanup_failed")))
    })
  }
}

/**
 * The confirmation is a window of ours, under the tour's layer: while it is
 * asked the tour steps aside, or its dim would cover the question.
 */
const confirming = ref(false)

async function stop() {
  confirming.value = true
  const accepted = await confirm({
    title: t("onboarding.close_title"),
    message: t("onboarding.close_message"),
    confirmLabel: t("onboarding.close_confirm"),
    cancelLabel: t("onboarding.keep_going"),
  }).finally(() => {
    confirming.value = false
  })
  if (accepted) close()
}

// A tour without a closing card ends on its last chapter, leaving the screen
// as the person has it: the welcome's ends with the catalog open (D355).
watch(tourFinished, (finished) => {
  if (finished && closing.value === null) close()
})

function next() {
  nextChapter()
}

const router = useRouter()

/** Finished all the same, then the list of tours in Preferences. */
function moreTours() {
  close()
  void router.push({ name: "preferences", params: { section: "tours" satisfies PreferenceSectionId } })
}
</script>

<template>
  <Teleport to="body">
    <template v-if="running && !confirming">
      <div
        v-if="ring"
        class="tour-ring"
        :style="ringStyle"
        data-testid="tour-ring"
      />
      <div
        v-else-if="tourFinished || tourState.preparing"
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
            v-if="!tourFinished && !tourState.preparing"
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
          <template v-if="!tourFinished">
            <AppButton
              v-if="!finishOnly"
              variant="quiet"
              :label="t('onboarding.end_tour')"
              data-testid="tour-end"
              @click="stop"
            />
            <AppButton
              v-if="offersMoreTours"
              variant="quiet"
              :label="t('onboarding.more_tours')"
              data-testid="tour-more"
              @click="moreTours"
            />
            <AppButton
              v-if="canNext || finishOnly"
              :label="isLast ? t('onboarding.finish') : t('onboarding.next')"
              data-testid="tour-next"
              @click="next"
            />
          </template>
          <AppButton
            v-else
            :label="t('onboarding.finish')"
            data-testid="tour-finish"
            @click="close"
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
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--dp-space-2);
}
</style>
