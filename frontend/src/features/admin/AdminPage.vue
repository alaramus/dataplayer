<script setup lang="ts">
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import UsersSection from "@/features/admin/UsersSection.vue"
import { ADMIN_SECTIONS } from "@/features/admin/sections"
import type { AdminSectionId } from "@/features/admin/sections"
import { useCurrentUser } from "@/shared/auth/currentUser"
import { t } from "@/shared/i18n"
import { AppButton, AppEmptyState, AppLayout, AppPageHeader, AppSectionsLayout, sectionOf } from "@/shared/ui"

/**
 * Administering this installation: a list of sections beside what one of them
 * shows. There is one section today, and what comes next arrives as an entry
 * in `sections.ts` rather than as a rearrangement of this screen.
 *
 * The address names the section, so a link into one is a link and the back
 * button walks between them.
 */
const route = useRoute()
const router = useRouter()
const me = useCurrentUser()

const current = computed(() =>
  sectionOf(ADMIN_SECTIONS, typeof route.params.section === "string" ? route.params.section : undefined)
)

/** Which component draws the section. A table, for the reason every other
    table in this repository is one: a second section is a line. */
const BODIES: Record<AdminSectionId, typeof UsersSection> = {
  users: UsersSection,
}

const body = computed(() => BODIES[current.value.id])

const isAdmin = computed(() => me.data.value?.is_superuser === true)

function show(id: string) {
  void router.replace({ name: "admin", params: { section: id } })
}
</script>

<template>
  <AppLayout fill>
    <div
      class="app-layout__surface"
      data-testid="admin-page-surface"
    >
      <!-- The heading names the page and the list names the section: a header
           that repeated the section would be saying it twice, and AppPageHeader
           takes a title and nothing else. -->
      <AppPageHeader :title="t('admin.title')">
        <template #actions>
          <AppButton
            variant="quiet"
            :label="t('common.back_to_workspace')"
            data-testid="back-to-workspace"
            @click="router.push({ name: 'workspace' })"
          />
        </template>
      </AppPageHeader>

      <!-- The routes behind every section answer 403 to everybody else; this
           says so once, here, rather than in each section separately. -->
      <AppEmptyState
        v-if="me.isFetched.value && !isAdmin"
        :text="t('admin.only_admin')"
      />

      <AppSectionsLayout
        v-else
        :sections="ADMIN_SECTIONS"
        :current="current.id"
        testid="admin"
        @select="show"
      >
        <component :is="body" />
      </AppSectionsLayout>
    </div>
  </AppLayout>
</template>

