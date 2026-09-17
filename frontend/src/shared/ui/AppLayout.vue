<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import ToastHost from "@/shared/notifications/ToastHost.vue"
import { resetNotices } from "@/shared/notifications/notices"
import { useCurrentUser } from "@/shared/auth/currentUser"
import { closeRealtime } from "@/shared/realtime/client"
import WindowTaskbar from "@/shared/windows/WindowTaskbar.vue"
import { windowsApiKey } from "@/shared/windows/useWindows"
import { useAuthStore } from "@/stores/auth"

import AppButton from "./AppButton.vue"
import AppFullscreenToggle from "./AppFullscreenToggle.vue"
import AppMenu from "./AppMenu.vue"
import type { MenuItem } from "./AppMenu.vue"
import AppTooltip from "./AppTooltip.vue"

defineProps<{ fill?: boolean }>()

const auth = useAuthStore()
const me = useCurrentUser()
const router = useRouter()
const queryClient = useQueryClient()
const windows = inject(windowsApiKey, undefined)
const footer = ref<HTMLElement | null>(null)
// Measured for the cards as well as for the windows: a screen with no window
// manager still has a footer, and a card must sit above it there too.
const footerHeight = ref(0)
const userMenuOpen = ref(false)
let footerObserver: ResizeObserver | null = null

const userMenuItems = computed<MenuItem[]>(() => {
  const items: MenuItem[] = [
    { name: "preferences", label: "Preferences", icon: "tune" },
  ]
  if (me.data.value?.is_superuser === true) {
    items.push({ name: "admin", label: "Admin", icon: "admin_panel_settings" })
  }
  items.push({ name: "logout", label: "Sign out", icon: "logout" })
  return items
})

async function selectUserAction(name: string) {
  if (name === "preferences") {
    await router.push({ name: "preferences" })
  } else if (name === "admin") {
    await router.push({ name: "admin" })
  } else if (name === "logout") {
    await logout()
  }
}

onMounted(() => {
  if (footer.value === null) return
  const measure = () => {
    footerHeight.value = footer.value?.getBoundingClientRect().height ?? 0
    windows?.setBottomInset(footerHeight.value)
  }
  measure()
  if (typeof ResizeObserver !== "undefined") {
    footerObserver = new ResizeObserver(measure)
    footerObserver.observe(footer.value)
  }
})

onBeforeUnmount(() => {
  footerObserver?.disconnect()
  windows?.setBottomInset(0)
})

async function logout() {
  auth.clear()
  closeRealtime()
  // What was said was said to whoever was here before.
  resetNotices()
  // The cache is cleared on sign-out: otherwise the previous user's data stays
  // visible to the next one.
  queryClient.clear()
  await router.push({ name: "login" })
}
</script>

<template>
  <q-layout
    view="hHh lpR fFf"
    class="app-layout"
    :class="fill ? 'app-layout--fill' : undefined"
  >
    <q-header
      class="app-layout__header"
      data-testid="app-header"
    >
      <q-toolbar class="app-layout__toolbar">
        <!-- Whatever the page puts first — on the workspace, the button that
             collapses the first panel of the space being shown. The fullscreen
             toggle and the user menu on the right. Workspace commands live on
             the side tool rails, and the theme switch in the user
             preferences. -->
        <q-toolbar-title class="app-layout__title">
          <slot name="header-start" />
        </q-toolbar-title>
        <q-space />
        <AppFullscreenToggle />
        <AppButton
          variant="quiet"
          size="sm"
          icon="account_circle"
          aria-label="User menu"
          aria-haspopup="menu"
          :aria-expanded="userMenuOpen"
          data-testid="user-menu"
        >
          <AppTooltip>User menu</AppTooltip>
          <AppMenu
            v-model="userMenuOpen"
            :items="userMenuItems"
            anchor="bottom right"
            self="top right"
            @select="selectUserAction"
          />
        </AppButton>
      </q-toolbar>
      <slot name="header-overlay" />
    </q-header>
    <q-page-container class="app-layout__body">
      <q-page
        :padding="!fill"
        class="app-layout__page"
        data-testid="app-page"
        :class="fill ? 'app-layout__page--fill' : undefined"
      >
        <div :class="fill ? 'app-layout__content app-layout__content--fill' : 'app-layout__content'">
          <slot />
        </div>
      </q-page>
    </q-page-container>

    <!-- One row for what is open: the sections put aside, then the windows,
         the way a desktop puts its taskbar beside the rest of its bar rather
         than under it. -->
    <q-footer
      class="app-layout__footer"
      data-testid="app-footer"
    >
      <div
        ref="footer"
        class="app-layout__status"
      >
        <slot name="status" />
        <!-- After the status commands: what is open on this screen. It takes
             the room left over, so a row of windows scrolls rather than
             pushing the end of the bar off screen. -->
        <WindowTaskbar
          v-if="windows"
          :context="windows.context"
        />
        <div
          v-if="$slots['status-end']"
          class="app-layout__status-end"
        >
          <slot name="status-end" />
        </div>
      </div>
    </q-footer>

    <ToastHost :bottom="footerHeight" />
  </q-layout>
</template>

<style scoped>
.app-layout {
  background: var(--dp-chrome-raised);
}

.app-layout__body {
  margin-inline: var(--dp-shell-side-width);
}

/* A filling page goes edge to edge: the side rails stand flush against the
   window instead of being pulled past the page bounds (which the page below
   clips). */
.app-layout--fill .app-layout__body {
  margin-inline: 0;
}

.app-layout__page {
  background: var(--dp-surface);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-shell);
  overflow: clip;
}

.app-layout__header,
.app-layout__footer {
  background: var(--dp-chrome-raised);
  color: var(--dp-text-strong);
  box-shadow: none;
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
  /* No Quasar's own side padding: a page aligns its leading control with
     the rails below pixel for pixel. */
  padding: 0;
}

/* The status bar starts and ends set off the edges the way the user menu is
   in the header; the window tabs then start in line with the first card. */
.app-layout__status {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: var(--dp-status-height);
  padding: 0 var(--dp-space-2);
  font-size: 12px;
}

/* margin-left keeps it at the end on a screen with no taskbar to take the
   space between. */
.app-layout__status-end {
  margin-left: auto;
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
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
  border: none;
  border-radius: 0;
  background: var(--dp-chrome-raised);
}

.app-layout__content--fill {
  flex: 1;
  min-height: 0;
  display: flex;
  background: var(--dp-chrome-raised);
}

.app-layout__content--fill > * {
  flex: 1;
  min-height: 0;
}
</style>
