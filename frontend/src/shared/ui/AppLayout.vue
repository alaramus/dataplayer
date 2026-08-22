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
  <q-layout
    view="hHh lpR fFf"
    :class="fill ? 'app-layout--fill' : undefined"
  >
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
}

:deep(.app-layout__page--fill) > * {
  flex: 1;
  min-height: 0;
}
</style>
