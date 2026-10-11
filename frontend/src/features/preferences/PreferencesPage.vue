<script setup lang="ts">
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import SshKeysSection from "@/features/sshKeys/SshKeysSection.vue"
import { t } from "@/shared/i18n"
import { AppButton, AppLayout, AppPageHeader, AppSectionsLayout, sectionOf } from "@/shared/ui"

import ConnectionsSection from "./ConnectionsSection.vue"
import GeneralSection from "./GeneralSection.vue"
import { PREFERENCE_SECTIONS } from "./sections"
import type { PreferenceSectionId } from "./sections"

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
  sectionOf(PREFERENCE_SECTIONS, typeof route.params.section === "string" ? route.params.section : undefined)
)

/** Which component draws the section. A table, for the reason every other
    table in this repository is one: a second section is a line. */
const BODIES: Record<PreferenceSectionId, typeof GeneralSection> = {
  general: GeneralSection,
  connections: ConnectionsSection,
  "ssh-keys": SshKeysSection,
}

const body = computed(() => BODIES[current.value.id])

function show(id: string) {
  void router.replace({ name: "preferences", params: { section: id } })
}
</script>

<template>
  <AppLayout fill>
    <div
      class="app-layout__surface"
      data-testid="preferences-page-surface"
    >
      <!-- The heading names the page and the list names the section: a header
           that repeated the section would be saying it twice, and AppPageHeader
           takes a title and nothing else. -->
      <AppPageHeader :title="t('preferences.title')">
        <template #actions>
          <AppButton
            variant="quiet"
            :label="t('common.back_to_workspace')"
            data-testid="back-to-workspace"
            @click="router.push({ name: 'workspace' })"
          />
        </template>
      </AppPageHeader>

      <AppSectionsLayout
        :sections="PREFERENCE_SECTIONS"
        :current="current.id"
        testid="preferences"
        @select="show"
      >
        <component :is="body" />
      </AppSectionsLayout>
    </div>
  </AppLayout>
</template>

