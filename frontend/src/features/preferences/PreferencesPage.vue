<script setup lang="ts">
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import SshKeysSection from "@/features/sshKeys/SshKeysSection.vue"
import { AppButton, AppLayout, AppPageHeader } from "@/shared/ui"

import ConnectionsSection from "./ConnectionsSection.vue"
import GeneralSection from "./GeneralSection.vue"
import { PREFERENCE_SECTIONS, sectionFor } from "./sections"

/**
 * What this account chose for itself: a list of sections beside what one of
 * them shows, the way Administration reads. There are three sections today,
 * and what comes next arrives as an entry in `sections.ts` rather than as a
 * rearrangement of this screen.
 *
 * The address names the section, so a link into one is a link and the back
 * button walks between them.
 */
const route = useRoute()
const router = useRouter()

const current = computed(() =>
  sectionFor(typeof route.params.section === "string" ? route.params.section : undefined)
)

/** Which component draws the section. A table, for the reason every other
    table in this repository is one: a second section is a line. */
const BODIES: Record<string, typeof GeneralSection> = {
  general: GeneralSection,
  connections: ConnectionsSection,
  "ssh-keys": SshKeysSection,
}

const body = computed(() => BODIES[current.value.id] ?? null)

function show(id: string) {
  void router.replace({ name: "preferences", params: { section: id } })
}
</script>

<template>
  <AppLayout fill>
    <div
      class="app-layout__surface preferences-page"
      data-testid="preferences-page-surface"
    >
      <!-- The heading names the page and the list names the section: a header
           that repeated the section would be saying it twice, and AppPageHeader
           takes a title and nothing else. -->
      <AppPageHeader title="Preferences">
        <template #actions>
          <AppButton
            variant="quiet"
            label="Back to workspace"
            data-testid="back-to-workspace"
            @click="router.push({ name: 'workspace' })"
          />
        </template>
      </AppPageHeader>

      <div
        class="preferences"
        data-testid="preferences"
      >
        <nav
          class="preferences__sections"
          data-testid="preferences-sections"
        >
          <button
            v-for="section in PREFERENCE_SECTIONS"
            :key="section.id"
            type="button"
            class="preferences__section"
            :class="{ 'preferences__section--current': section.id === current.id }"
            :data-testid="`preferences-section-${section.id}`"
            @click="show(section.id)"
          >
            <q-icon
              :name="section.icon"
              size="var(--dp-icon-sm)"
            />
            <span class="preferences__section-text">
              <span class="preferences__section-title">{{ section.title }}</span>
              <span class="preferences__section-summary">{{ section.summary }}</span>
            </span>
          </button>
        </nav>

        <section class="preferences__body">
          <component :is="body" />
        </section>
      </div>
    </div>
  </AppLayout>
</template>

<style scoped>
.preferences {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: var(--dp-space-5);
  align-items: start;
  min-height: 0;
}

.preferences__sections {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
}

.preferences__section {
  display: flex;
  align-items: flex-start;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-3);
  border: 0;
  border-radius: var(--dp-radius-control);
  background: transparent;
  color: var(--dp-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.preferences__section:hover {
  background: var(--dp-hover);
}

/* The section shown is the current page of a list, marked as a tab is (D186). */
.preferences__section--current {
  background: var(--dp-tab-current);
}

.preferences__section-text {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-half);
  min-width: 0;
}

.preferences__section-title {
  font-weight: 500;
}

.preferences__section-summary {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}

.preferences__body {
  min-width: 0;
}

/* A narrow window puts the list above what it opens rather than beside it. */
@media (max-width: 900px) {
  .preferences {
    grid-template-columns: 1fr;
  }
}
</style>
