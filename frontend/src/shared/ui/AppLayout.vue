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
      <q-page :padding="!fill">
        <slot />
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<style scoped>
:deep(.q-page) {
  display: flex;
  flex-direction: column;
}
</style>
