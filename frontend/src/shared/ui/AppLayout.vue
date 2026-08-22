<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { useRouter } from "vue-router"

import { useAuthStore } from "@/stores/auth"

import AppButton from "./AppButton.vue"

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
  <q-layout view="hHh lpR fFf">
    <q-header elevated>
      <q-toolbar>
        <q-toolbar-title>DataPlayer</q-toolbar-title>
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
        <slot />
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<style scoped>
/* A filling page hands its whole height to what it holds: Quasar gives the
   page a min-height and nothing else, so a child asking for 100% of an
   auto-height parent gets the height of its own content instead. Scoped to
   the fill case — an ordinary page is a document that grows downwards. */
:deep(.app-layout__page--fill) {
  display: flex;
  flex-direction: column;
}

:deep(.app-layout__page--fill) > * {
  flex: 1 1 auto;
  min-height: 0;
}
</style>
