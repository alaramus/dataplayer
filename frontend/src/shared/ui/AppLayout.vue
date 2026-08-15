<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { useRouter } from "vue-router"

import { useAuthStore } from "@/stores/auth"

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
        <q-btn
          flat
          dense
          label="Sign out"
          data-testid="logout"
          @click="logout"
        />
      </q-toolbar>
    </q-header>
    <q-page-container>
      <q-page padding>
        <slot />
      </q-page>
    </q-page-container>
  </q-layout>
</template>
