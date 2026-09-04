<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { useCurrentUser } from "@/shared/auth/currentUser"
import ServerSwitcher from "@/features/servers/ServerSwitcher.vue"
import { closeRealtime } from "@/shared/realtime/client"
import WindowTaskbar from "@/shared/windows/WindowTaskbar.vue"
import { windowsApiKey } from "@/shared/windows/useWindows"
import { useAuthStore } from "@/stores/auth"
import { useThemeStore } from "@/stores/theme"

import AppButton from "./AppButton.vue"
import AppMenu from "./AppMenu.vue"
import type { MenuItem } from "./AppMenu.vue"
import AppThemeToggle from "./AppThemeToggle.vue"
import AppTooltip from "./AppTooltip.vue"

defineProps<{ fill?: boolean }>()

const auth = useAuthStore()
const me = useCurrentUser()
const theme = useThemeStore()
const router = useRouter()
const queryClient = useQueryClient()
const windows = inject(windowsApiKey, undefined)
const footer = ref<HTMLElement | null>(null)
const userMenuOpen = ref(false)
let footerObserver: ResizeObserver | null = null

const userMenuItems = computed<MenuItem[]>(() => {
  const items: MenuItem[] = []
  if (me.data.value?.is_superuser === true) {
    items.push({ name: "admin", label: "Admin", icon: "admin_panel_settings" })
  }
  items.push({ name: "logout", label: "Sign out", icon: "logout" })
  return items
})

async function selectUserAction(name: string) {
  if (name === "admin") {
    await router.push({ name: "admin" })
  } else if (name === "logout") {
    await logout()
  }
}

onMounted(() => {
  if (footer.value === null || windows === undefined) return
  const measure = () => windows.setBottomInset(footer.value?.getBoundingClientRect().height ?? 0)
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
        <q-toolbar-title
          class="app-layout__title"
          :class="{ 'app-layout__title--compact': $slots['workspace-tools'] }"
        >
          <img
            :src="theme.dark ? '/icons/logodpW.svg' : '/icons/logodp.svg'"
            alt=""
            width="16"
            height="16"
            class="app-layout__logo"
          >
          <span>DataPlayer</span>
        </q-toolbar-title>
        <slot name="workspace-tools" />
        <!-- Page actions precede the theme control and the account menu. -->
        <slot name="actions" />
        <AppThemeToggle />
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

    <!-- The status commands and minimized windows share one measured footer. -->
    <q-footer
      class="app-layout__footer"
      data-testid="app-footer"
    >
      <div
        ref="footer"
        class="app-layout__footer-content"
      >
        <div class="app-layout__status">
          <ServerSwitcher />
          <slot name="status" />
          <div
            v-if="$slots['status-end']"
            class="app-layout__status-end"
          >
            <slot name="status-end" />
          </div>
        </div>
        <WindowTaskbar
          v-if="windows"
          :context="windows.context"
        />
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

.app-layout__footer-content {
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

.app-layout__title--compact {
  flex: none;
}

.app-layout__logo {
  flex: none;
  object-fit: contain;
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

.app-layout__status-end { margin-left: auto; flex: none; }

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
