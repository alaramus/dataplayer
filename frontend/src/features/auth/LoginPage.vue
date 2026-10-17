<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { useLogin } from "@/features/auth/api"
import { requiredCredentialErrors } from "./validation"
import { useActiveServerCheck } from "@/features/servers/api"
import ServerSwitcher from "@/features/servers/ServerSwitcher.vue"
import { t } from "@/shared/i18n"
import { safeLocalPath } from "@/shared/servers/profiles"
import { useServersStore } from "@/stores/servers"
import { AppBanner, AppButton, AppCard, AppForm, AppInput } from "@/shared/ui"

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
const submitted = ref(false)
const errors = computed(() => submitted.value
  ? requiredCredentialErrors(username.value, password.value)
  : { username: "", password: "" }
)

watch([username, password], () => { failed.value = false })

async function submit() {
  if (!serverStatus.isSuccess.value) return
  failed.value = false
  submitted.value = true
  if (errors.value.username || errors.value.password) return
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
  <div class="login-page">
    <AppCard
      size="xs"
      :title="t('auth.sign_in')"
    >
      <q-form @submit.prevent="submit">
        <AppForm layout="section">
          <div class="login-server">
            <ServerSwitcher />
            <div class="login-server-url">
              {{ servers.active.url }}
            </div>
          </div>
          <div
            v-if="serverStatus.isPending.value"
            class="login-server-url"
          >
            {{ t('auth.checking_server') }}
          </div>
          <AppBanner
            v-if="serverStatus.isError.value"
            tone="error"
          >
            {{ serverStatus.error.value?.message }}
            <AppButton
              :label="t('auth.retry_connection')"
              variant="quiet"
              :loading="serverStatus.isFetching.value"
              @click="serverStatus.refetch()"
            />
          </AppBanner>
          <AppInput
            v-model="username"
            :label="t('auth.email')"
            type="email"
            autocomplete="username"
            aria-required="true"
            :error="errors.username"
            data-testid="login-email"
          />
          <AppInput
            v-model="password"
            :label="t('auth.password')"
            type="password"
            autocomplete="current-password"
            aria-required="true"
            :error="errors.password"
            data-testid="login-password"
          />
          <AppBanner
            v-if="failed"
            tone="error"
            data-testid="login-error"
          >
            {{ t('auth.sign_in_failed') }}
          </AppBanner>
          <!-- In the form's own column, so its edges are the fields' edges:
               in the card's actions it stood 8px past them on each side. -->
          <AppButton
            type="submit"
            :label="t('auth.sign_in')"
            data-testid="login-submit"
            :loading="login.isPending.value"
            :disable="!serverStatus.isSuccess.value"
          />
        </AppForm>
      </q-form>
    </AppCard>
  </div>
</template>

<style scoped>
/* The ground of the application's chrome, as behind every other card. */
.login-page { min-height: 100vh; display: grid; place-items: center; padding: var(--dp-space-4); background: var(--dp-chrome-raised); }
/* Content-sized and at the start of the column, not stretched across it with
   its icon and name floating in the middle. */
.login-server { display: flex; flex-direction: column; align-items: flex-start; gap: var(--dp-space-1); }
.login-server-url { font-size: var(--dp-font-size-sm); color: var(--dp-text-muted); overflow-wrap: anywhere; }
</style>
