<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { useRouter } from "vue-router"

import { useAuthStore } from "@/stores/auth"

import AppButton from "./AppButton.vue"
import AppThemeToggle from "./AppThemeToggle.vue"

defineProps<{ fill?: boolean }>()

const auth = useAuthStore()
const router = useRouter()
const queryClient = useQueryClient()

async function logout() {
  auth.clear()
  // The cache is cleared on sign-out: otherwise the previous user's data stays
  // visible to the next one.
  queryClient.clear()
  await router.push({ name: "login" })
}
</script>

<template>
  <q-layout
    view="hHh lpR fFf"
    :class="fill ? 'app-layout--fill' : undefined"
  >
    <q-header class="app-layout__header">
      <q-toolbar class="app-layout__toolbar">
        <q-toolbar-title class="app-layout__title">
          <span>DataPlayer</span>
        </q-toolbar-title>
        <!-- What a screen wants in the header, before the two things that
             belong to the session. The kit knows no feature: whoever renders
             the layout decides what goes here. -->
        <slot name="actions" />
        <!-- Beside signing out: both are about this session rather than about
             what is on the screen. -->
        <AppThemeToggle />
        <AppButton
          variant="quiet"
          size="sm"
          label="Sign out"
          data-testid="logout"
          @click="logout"
        />
      </q-toolbar>
    </q-header>
    <q-page-container>
      <q-page
        :padding="!fill"
        :class="fill ? 'app-layout__page--fill' : undefined"
      >
        <div :class="fill ? 'app-layout__content app-layout__content--fill' : 'app-layout__content'">
          <slot />
        </div>
      </q-page>
    </q-page-container>

    <!-- A bar of the same colour as the header, closing the screen at the
         bottom. Empty on purpose: what belongs in a status bar - what is
         connected, what is running, what the last request cost - arrives with
         the work that produces it, and the room for it is here. -->
    <q-footer
      class="app-layout__footer"
      data-testid="app-footer"
    >
      <div class="app-layout__status">
        <slot name="status" />
      </div>
    </q-footer>
  </q-layout>
</template>

<style scoped>
.app-layout__header,
.app-layout__footer {
  background: var(--dp-chrome-raised);
  color: var(--dp-text-strong);
  box-shadow: none;
}

.app-layout__header {
  border-bottom: 1px solid var(--dp-border);
}

.app-layout__footer {
  border-top: 1px solid var(--dp-border);
}

.app-layout__toolbar {
  min-height: var(--dp-header-height);
  padding: 0 var(--dp-space-2) 0 var(--dp-space-3);
}

.app-layout__title {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.01em;
}

/* Shorter than the toolbar above it: it is a line, not a second header. */
.app-layout__status {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: var(--dp-status-height);
  padding: 0 var(--dp-space-3);
  font-size: 12px;
}

/* A filling page hands its whole height to what it holds, and that has to be
   said at every step down from the viewport: Quasar gives the layout and the
   page a min-height and nothing else, and a min-height alone still grows with
   its content — which is how a list of a hundred and fifty rows pushed the
   whole document taller instead of scrolling inside its own column.
   Scoped to the fill case: an ordinary page is a document that grows
   downwards. Quasar sets border-box everywhere, so the padding the container
   keeps for the header comes out of the 100% rather than adding to it. */
.app-layout--fill {
  height: 100vh;
  background: var(--dp-chrome);
}

.app-layout--fill :deep(.q-page-container) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

:deep(.app-layout__page--fill) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.app-layout__content--fill {
  flex: 1;
  min-height: 0;
  display: flex;
  padding: var(--dp-workspace-inset);
  background: var(--dp-chrome);
}

.app-layout__content--fill > * {
  flex: 1;
  min-height: 0;
}
</style>
