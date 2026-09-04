<script setup lang="ts">
import { ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { useLogin } from "@/features/auth/api"
import { useActiveServerCheck } from "@/features/servers/api"
import ServerSwitcher from "@/features/servers/ServerSwitcher.vue"
import { safeLocalPath } from "@/shared/servers/profiles"
import { useServersStore } from "@/stores/servers"
import { AppActions, AppBanner, AppButton, AppCard, AppInput, AppSection } from "@/shared/ui"

const router = useRouter()
const route = useRoute()
const login = useLogin()
const servers = useServersStore()
const serverStatus = useActiveServerCheck()

/**
 * Where to go once signed in.
 *
 * A link opened while signed out sends the person here, and sending them to an
 * empty workspace afterwards would lose what they came for. Only a path of
 * this application is followed: `next` comes from a URL, so anything that is
 * not a local path is ignored rather than navigated to.
 */
function afterSignIn(): string | null {
  return safeLocalPath(route.query.next)
}

const username = ref("")
const password = ref("")
const failed = ref(false)

async function submit() {
  if (!serverStatus.isSuccess.value) return
  failed.value = false
  try {
    await login.mutateAsync({ username: username.value, password: password.value })
    const next = afterSignIn()
    await (next === null ? router.push({ name: "workspace" }) : router.push(next))
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
              <ServerSwitcher />
              <div class="login-server-url">
                {{ servers.active.url }}
              </div>
              <div
                v-if="serverStatus.isPending.value"
                class="login-server-url"
              >
                Checking server…
              </div>
              <AppBanner
                v-if="serverStatus.isError.value"
                tone="error"
              >
                {{ serverStatus.error.value?.message }}
                <AppButton
                  label="Retry connection"
                  variant="quiet"
                  :loading="serverStatus.isFetching.value"
                  @click="serverStatus.refetch()"
                />
              </AppBanner>
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
                :disable="!serverStatus.isSuccess.value"
              />
            </AppActions>
          </q-form>
        </AppCard>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<style scoped>
.login-server-url { font-size: 12px; color: var(--dp-text-muted); overflow-wrap: anywhere; }
</style>
