<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { onBeforeUnmount, onMounted } from "vue"

import { notices } from "@/shared/notifications"
import type { AttentionItem } from "@/shared/notifications"
import { AppButton, AppEmptyState, AppIconButton, AppToggle, bannerLook, toneText } from "@/shared/ui"
import ProcessList from "./ProcessList.vue"
import type { ProcessRow } from "./presentation"

/**
 * Everything that needs a person, in one sheet along the right edge (D113).
 *
 * Three sections, because they behave differently: what is waiting stays until
 * it is dealt with, what is working ends by itself, and what happened is only
 * a record. A single list makes the first of the three unfindable. One thing
 * is in one of them at a time: a job leaves Working when it ends, for Recent
 * or for Needs you, and is not also listed where it used to be (D181).
 *
 * Not a floating window: a window is a piece of work somebody opened, and this
 * is the application talking about the work. Not modal and undimmed either —
 * the reason to open it is to watch something while carrying on.
 */
const props = defineProps<{
  attention: AttentionItem[]
  rows: ProcessRow[]
  error: string
  loading: boolean
  more: boolean
  stopping: ReadonlySet<string>
  /** Room taken by the application footer, so the sheet stops above it. */
  bottom: number
}>()

const emit = defineEmits<{
  close: []
  pause: [row: ProcessRow]
  resume: [row: ProcessRow]
  stop: [row: ProcessRow]
  more: []
  refresh: []
}>()

const log = notices()

function onKey(event: KeyboardEvent) {
  if (event.key === "Escape") emit("close")
}

onMounted(() => { window.addEventListener("keydown", onKey) })
onBeforeUnmount(() => { window.removeEventListener("keydown", onKey) })

const working = () => props.rows.filter((row) => row.active).length

/**
 * Every action here leads somewhere else, so the sheet gets out of the way.
 *
 * It floats over the work and swallows the first click anywhere outside
 * itself, which is right for a flyout and wrong for one that has just opened
 * a window to work in: leaving it up made "Open" a two-click movement, the
 * first click only closing the sheet.
 */
function follow(run: () => void) {
  emit("close")
  run()
}
</script>

<template>
  <Teleport to="body">
    <!-- No scrim: dimming the application would say it had stopped, and the
         reason to open this is to watch it carry on. -->
    <div
      class="sheet__away"
      :style="{ bottom: `${bottom}px` }"
      @click="emit('close')"
    />
    <aside
      class="sheet"
      :style="{ bottom: `calc(${bottom}px + var(--dp-space-1))` }"
      role="complementary"
      aria-label="Activity"
      data-testid="activity-panel"
    >
      <header class="sheet__bar">
        <strong>Activity</strong>
        <AppToggle
          :model-value="log.doNotDisturb.value"
          label="Do not disturb"
          data-testid="do-not-disturb"
          @update:model-value="log.setDoNotDisturb($event)"
        />
        <AppIconButton
          :icon="appIcons.close"
          tooltip="Close"
          @click="emit('close')"
        />
      </header>

      <div class="sheet__body">
        <section
          class="sheet__section"
          data-testid="attention-section"
        >
          <h3 class="sheet__heading">
            <span>Needs you</span>
            <span
              v-if="attention.length > 0"
              class="sheet__count"
            >{{ attention.length }}</span>
          </h3>
          <AppEmptyState
            v-if="attention.length === 0"
            text="Nothing is waiting for you"
          />
          <article
            v-for="item in attention"
            :key="item.id"
            class="sheet__item"
            :data-testid="`attention-${item.id}`"
          >
            <q-icon
              :name="bannerLook(item.tone).icon"
              :class="toneText(item.tone)"
              size="18px"
            />
            <div class="sheet__text">
              <strong>{{ item.title }}</strong>
              <p>{{ item.detail }}</p>
              <p
                v-for="(line, index) in item.lines ?? []"
                :key="index"
                class="sheet__line"
              >
                {{ line }}
              </p>
            </div>
            <AppButton
              v-if="item.action"
              variant="secondary"
              size="sm"
              :label="item.action.label"
              @click="follow(item.action.run)"
            />
            <AppIconButton
              v-if="item.dismiss"
              :icon="appIcons.close"
              tooltip="Dismiss"
              compact
              @click="item.dismiss()"
            />
          </article>
        </section>

        <section
          class="sheet__section"
          data-testid="working-section"
        >
          <h3 class="sheet__heading">
            <span>Working</span>
            <span
              v-if="working() > 0"
              class="sheet__count"
            >{{ working() }}</span>
            <AppButton
              variant="quiet"
              size="sm"
              label="Refresh"
              :loading="loading"
              @click="emit('refresh')"
            />
          </h3>
          <ProcessList
            :rows="rows"
            :error="error"
            :loading="loading"
            :more="more"
            :stopping="stopping"
            @pause="emit('pause', $event)"
            @resume="emit('resume', $event)"
            @stop="emit('stop', $event)"
            @more="emit('more')"
          />
        </section>

        <section
          class="sheet__section"
          data-testid="recent-section"
        >
          <h3 class="sheet__heading">
            <span>Recent</span>
            <AppButton
              v-if="log.entries.value.length > 0"
              variant="quiet"
              size="sm"
              label="Clear all"
              @click="log.forgetAll()"
            />
          </h3>
          <AppEmptyState
            v-if="log.entries.value.length === 0"
            text="Nothing has been said yet"
          />
          <article
            v-for="notice in log.entries.value"
            :key="notice.id"
            class="sheet__item"
            data-testid="notice"
          >
            <q-icon
              :name="bannerLook(notice.tone).icon"
              :class="toneText(notice.tone)"
              size="18px"
            />
            <div class="sheet__text">
              <strong v-if="notice.title">{{ notice.title }}</strong>
              <p>{{ notice.message }}</p>
              <p
                v-for="(line, index) in notice.lines ?? []"
                :key="index"
                class="sheet__line"
              >
                {{ line }}
              </p>
              <time
                class="sheet__when"
                :datetime="new Date(notice.at).toISOString()"
              >{{ new Date(notice.at).toLocaleTimeString() }}</time>
            </div>
            <AppButton
              v-if="notice.action"
              variant="secondary"
              size="sm"
              :label="notice.action.label"
              @click="follow(notice.action.run)"
            />
            <AppIconButton
              :icon="appIcons.close"
              tooltip="Remove"
              compact
              @click="log.forget(notice.id)"
            />
          </article>
        </section>
      </div>
    </aside>
  </Teleport>
</template>

<style scoped>
/* Over the work, floating windows included, and under the menus and dialogs
   that open from inside the sheet itself. */
.sheet, .sheet__away {
  position: fixed;
  top: var(--dp-header-height);
  z-index: var(--dp-layer-sheet);
}

/* Catches a click outside without painting anything: closing by clicking away
   is expected of a flyout, and a listener on the document would also catch the
   click that opened it. */
.sheet__away { left: 0; right: 0; }

.sheet {
  top: calc(var(--dp-header-height) + var(--dp-space-1));
  right: var(--dp-space-1);
  width: 380px;
  max-width: calc(100vw - var(--dp-space-2));
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
  background: var(--dp-surface);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  box-shadow: -8px 0 24px var(--dp-shadow-soft);
}

.sheet__bar {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-2) var(--dp-space-2) var(--dp-space-3);
  border-bottom: 1px solid var(--dp-border);
  background: var(--dp-card-head);
}

.sheet__bar > strong { flex: 1; }

.sheet__body { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; }

.sheet__section { padding: var(--dp-space-2) var(--dp-space-3) var(--dp-space-3); }
.sheet__section + .sheet__section { border-top: 1px solid var(--dp-border); }

.sheet__heading {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  margin: 0 0 var(--dp-space-2);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dp-text-muted);
}

.sheet__heading > span { flex: none; }
.sheet__count {
  padding: 0 var(--dp-space-2);
  border-radius: var(--dp-radius-pill);
  background: var(--dp-border);
  color: var(--dp-text-strong);
  letter-spacing: 0;
}

/* The count belongs beside the name of the section; the commands go to the
   far end together, so the first of them is what takes up the slack. */
.sheet__heading > button:first-of-type { margin-left: auto; }

.sheet__item {
  display: flex;
  align-items: flex-start;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) 0;
  border-top: 1px solid var(--dp-border-faint);
}
.sheet__item:first-of-type { border-top: none; }

.sheet__text { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.sheet__text p { margin: 0; }
.sheet__text strong + p { color: var(--dp-text-muted); }
/* The steps behind an entry: one to a line, quieter than what it says. */
.sheet__line { color: var(--dp-text-muted); }
.sheet__when { font-size: 11px; color: var(--dp-text-faint); }
</style>
