<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"

import { useLogin } from "@/features/auth/api"
import { AppActions, AppBanner, AppButton, AppCard, AppInput, AppSection } from "@/shared/ui"

const router = useRouter()
const login = useLogin()

const username = ref("")
const password = ref("")
const failed = ref(false)

async function submit() {
  failed.value = false
  try {
    await login.mutateAsync({ username: username.value, password: password.value })
    await router.push({ name: "connectors" })
  } catch {
    failed.value = true
  }
}
</script>

<template>
  <q-layout view="hHh lpR fFf">
    <q-page-container>
      <q-page class="flex flex-center">
        <AppCard
          size="xs"
          title="Sign in"
        >
          <q-form @submit.prevent="submit">
            <AppSection gutter>
              <AppInput
                v-model="username"
                label="Email"
                type="email"
                autocomplete="username"
                data-testid="login-email"
              />
              <AppInput
                v-model="password"
                label="Password"
                type="password"
                autocomplete="current-password"
                data-testid="login-password"
              />
              <AppBanner
                v-if="failed"
                tone="error"
                data-testid="login-error"
              >
                Could not sign in. Check the email and password.
              </AppBanner>
            </AppSection>
            <AppActions align="left">
              <AppButton
                type="submit"
                label="Sign in"
                class="full-width"
                data-testid="login-submit"
                :loading="login.isPending.value"
              />
            </AppActions>
          </q-form>
        </AppCard>
      </q-page>
    </q-page-container>
  </q-layout>
</template>
