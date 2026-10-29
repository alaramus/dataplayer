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
import { AppBanner, AppButton, AppForm, AppInput } from "@/shared/ui"

const router = useRouter()
const route = useRoute()
const login = useLogin()
const servers = useServersStore()
const serverStatus = useActiveServerCheck()

/** The product's name, which no language translates. */
const PRODUCT = "DataPlayer"

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
    <!-- The welcome half says what the product is before anyone has an
         account; it is decoration, so the form is the page's one landmark. -->
    <section
      class="login-welcome"
      aria-hidden="true"
    >
      <div class="login-welcome-body">
        <img
          class="login-logo"
          src="/icons/logodp.svg"
          alt=""
        >
        <div class="login-product">
          {{ PRODUCT }}
        </div>
        <p class="login-tagline">
          {{ t('auth.welcome_tagline') }}
        </p>
      </div>
    </section>
    <main class="login-side">
      <q-form
        class="login-form"
        @submit.prevent="submit"
      >
        <AppForm layout="section">
          <h1 class="dp-page-title login-title">
            {{ t('auth.sign_in') }}
          </h1>
          <q-separator />
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
          <q-separator />
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
          <AppButton
            type="submit"
            :label="t('auth.sign_in')"
            data-testid="login-submit"
            :loading="login.isPending.value"
            :disable="!serverStatus.isSuccess.value"
          />
        </AppForm>
      </q-form>
    </main>
  </div>
</template>

<style scoped>
.login-page { min-height: 100vh; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); background: var(--dp-surface); }
.login-welcome { display: grid; place-items: center; padding: var(--dp-space-5); background: linear-gradient(160deg, var(--dp-chrome) 0%, var(--dp-chrome-raised) 100%); border-inline-end: 1px solid var(--dp-border); }
.login-welcome-body { display: flex; flex-direction: column; align-items: center; gap: var(--dp-space-3); max-width: var(--dp-width-text); text-align: center; }
.login-logo { width: var(--dp-width-name); max-width: 50%; height: auto; margin-bottom: var(--dp-space-3); }
.login-product { font-size: var(--dp-font-size-display); font-weight: 600; color: var(--dp-text); }
.login-tagline { margin: 0; font-size: var(--dp-font-size-lg); color: var(--dp-text-muted); }
.login-side { display: grid; place-items: center; padding: var(--dp-space-5); }
.login-form { width: 100%; max-width: var(--dp-width-popover); }
.login-title { text-align: center; }
/* Content-sized and at the start of the column, not stretched across it with
   its icon and name floating in the middle. */
.login-server { display: flex; flex-direction: column; align-items: flex-start; gap: var(--dp-space-1); }
.login-server-url { font-size: var(--dp-font-size-sm); color: var(--dp-text-muted); overflow-wrap: anywhere; }
</style>
