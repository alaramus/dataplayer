<script setup lang="ts">
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import UsersSection from "@/features/admin/UsersSection.vue"
import { ADMIN_SECTIONS, sectionFor } from "@/features/admin/sections"
import { useCurrentUser } from "@/shared/auth/currentUser"
import { AppButton, AppEmptyState, AppLayout, AppPageHeader } from "@/shared/ui"

/**
 * Administering this installation.
 *
 * A list of sections beside what one of them shows. There is one section today
 * and the shape says so honestly: accounts are where administering an
 * installation starts, and what comes next — retention, service templates,
 * whatever the server grows — arrives as an entry in `sections.ts` and a line
 * in the table below rather than as a rearrangement of this screen.
 *
 * The address names the section, so a link into one of them is a link, and the
 * back button walks between them.
 */
const route = useRoute()
const router = useRouter()
const me = useCurrentUser()

const current = computed(() =>
  sectionFor(typeof route.params.section === "string" ? route.params.section : undefined)
)

/** Which component draws the section. A table, for the reason every other
    table in this repository is one: a second section is a line. */
const BODIES: Record<string, typeof UsersSection> = {
  users: UsersSection,
}

const body = computed(() => BODIES[current.value.id] ?? null)

const isAdmin = computed(() => me.data.value?.is_superuser === true)

function show(id: string) {
  void router.replace({ name: "admin", params: { section: id } })
}
</script>

<template>
  <AppLayout>
    <!-- The heading names the page and the list names the section: a header
         that repeated the section would be saying it twice, and AppPageHeader
         takes a title and nothing else. -->
    <AppPageHeader title="Administration">
      <template #actions>
        <AppButton
          variant="quiet"
          label="Back to workspace"
          data-testid="back-to-workspace"
          @click="router.push({ name: 'workspace' })"
        />
      </template>
    </AppPageHeader>

    <!-- The routes behind every section answer 403 to everybody else; this
         says so once, here, rather than in each section separately. -->
    <AppEmptyState
      v-if="me.isFetched.value && !isAdmin"
      text="Only an administrator manages this installation"
    />

    <div
      v-else
      class="admin"
    >
      <nav
        class="admin__sections"
        data-testid="admin-sections"
      >
        <button
          v-for="section in ADMIN_SECTIONS"
          :key="section.id"
          type="button"
          class="admin__section"
          :class="{ 'admin__section--current': section.id === current.id }"
          :data-testid="`admin-section-${section.id}`"
          @click="show(section.id)"
        >
          <q-icon
            :name="section.icon"
            size="18px"
          />
          <span class="admin__section-text">
            <span class="admin__section-title">{{ section.title }}</span>
            <span class="admin__section-summary">{{ section.summary }}</span>
          </span>
        </button>
      </nav>

      <section class="admin__body">
        <component :is="body" />
      </section>
    </div>
  </AppLayout>
</template>

<style scoped>
.admin {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 20px;
  align-items: start;
  min-height: 0;
}

.admin__sections {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.admin__section {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 0;
  border-radius: var(--dp-radius-control);
  background: transparent;
  color: var(--dp-text-strong);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.admin__section:hover {
  background: var(--dp-hover);
}

.admin__section--current {
  background: var(--dp-selected);
}

.admin__section-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.admin__section-title {
  font-weight: 500;
}

.admin__section-summary {
  color: var(--dp-text-muted);
  font-size: 12px;
}

.admin__body {
  min-width: 0;
}

/* A narrow window puts the list above what it opens rather than beside it. */
@media (max-width: 900px) {
  .admin {
    grid-template-columns: 1fr;
  }
}
</style>
