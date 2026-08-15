<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"

import { useLogin } from "@/features/auth/api"

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
        <q-card
          style="width: 360px"
          class="q-pa-md"
        >
          <q-card-section>
            <div class="text-h6">
              Вход
            </div>
          </q-card-section>
          <q-form @submit.prevent="submit">
            <q-card-section class="q-gutter-md">
              <q-input
                v-model="username"
                label="Электронная почта"
                type="email"
                autocomplete="username"
                data-testid="login-email"
              />
              <q-input
                v-model="password"
                label="Пароль"
                type="password"
                autocomplete="current-password"
                data-testid="login-password"
              />
              <q-banner
                v-if="failed"
                dense
                class="bg-negative text-white"
                data-testid="login-error"
              >
                Не удалось войти. Проверьте почту и пароль.
              </q-banner>
            </q-card-section>
            <q-card-actions>
              <q-btn
                type="submit"
                color="primary"
                class="full-width"
                label="Войти"
                data-testid="login-submit"
                :loading="login.isPending.value"
              />
            </q-card-actions>
          </q-form>
        </q-card>
      </q-page>
    </q-page-container>
  </q-layout>
</template>
