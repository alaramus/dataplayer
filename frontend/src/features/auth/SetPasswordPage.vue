<script setup lang="ts">
import { computed, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { useAcceptInvitation, useInvitationHolder } from "@/features/auth/api"
import AuthLayout from "./AuthLayout.vue"
import { newPasswordErrors } from "./validation"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppBanner, AppButton, AppForm, AppInput, AppSpinner } from "@/shared/ui"

/**
 * Where a person reached by a superuser's link chooses their password.
 *
 * Before this, the account has none and cannot sign in. The link works once:
 * the server forgets it the moment the password is set, so a page reloaded
 * afterwards says the link no longer works rather than asking again.
 */
const route = useRoute()
const router = useRouter()

const token = computed(() => (typeof route.query.token === "string" ? route.query.token : ""))
const holder = useInvitationHolder(token)
const accept = useAcceptInvitation()

const password = ref("")
const repeat = ref("")
const submitted = ref(false)
const done = ref(false)
const failure = ref("")

const errors = computed(() =>
  submitted.value ? newPasswordErrors(password.value, repeat.value) : { password: "", repeat: "" }
)
const unusable = computed(() => token.value === "" || holder.isError.value)

async function submit() {
  submitted.value = true
  failure.value = ""
  if (errors.value.password || errors.value.repeat) return
  try {
    await accept.mutateAsync({ token: token.value, new_password: password.value })
    done.value = true
  } catch (error) {
    failure.value = messageOf(error, t("auth.set_password.invalid"))
  }
}

function toSignIn() {
  void router.push({ name: "login" })
}
</script>

<template>
  <AuthLayout>
    <q-form
      class="set-password-form"
      @submit.prevent="submit"
    >
      <AppForm layout="section">
        <h1 class="dp-page-title set-password-title">
          {{ t('auth.set_password.title') }}
        </h1>

        <p
          v-if="holder.isPending.value && !unusable"
          class="set-password-note"
        >
          <AppSpinner inline />
          {{ t('auth.set_password.checking') }}
        </p>

        <template v-else-if="done">
          <AppBanner
            tone="success"
            data-testid="set-password-done"
          >
            {{ t('auth.set_password.done') }}
          </AppBanner>
          <AppButton
            :label="t('auth.set_password.to_sign_in')"
            data-testid="set-password-sign-in"
            @click="toSignIn"
          />
        </template>

        <template v-else-if="unusable">
          <AppBanner
            tone="warning"
            data-testid="set-password-invalid"
          >
            {{ t('auth.set_password.invalid') }}
          </AppBanner>
          <AppButton
            variant="quiet"
            :label="t('auth.set_password.to_sign_in')"
            @click="toSignIn"
          />
        </template>

        <template v-else>
          <p
            class="set-password-note"
            data-testid="set-password-holder"
          >
            {{ t('auth.set_password.for_whom', { email: holder.data.value?.email ?? '' }) }}
          </p>
          <!-- The address, for the browser's password manager to file the
               new password under. -->
          <input
            class="set-password-username"
            type="email"
            autocomplete="username"
            :value="holder.data.value?.email ?? ''"
            readonly
            tabindex="-1"
            aria-hidden="true"
          >
          <AppInput
            v-model="password"
            :label="t('auth.set_password.new')"
            type="password"
            autocomplete="new-password"
            aria-required="true"
            :error="errors.password"
            data-testid="set-password-new"
          />
          <AppInput
            v-model="repeat"
            :label="t('auth.set_password.repeat')"
            type="password"
            autocomplete="new-password"
            aria-required="true"
            :error="errors.repeat"
            data-testid="set-password-repeat"
          />
          <AppBanner
            v-if="failure"
            tone="error"
            data-testid="set-password-error"
          >
            {{ failure }}
          </AppBanner>
          <AppButton
            type="submit"
            :label="t('auth.set_password.submit')"
            :loading="accept.isPending.value"
            data-testid="set-password-submit"
          />
        </template>
      </AppForm>
    </q-form>
  </AuthLayout>
</template>

<style scoped>
.set-password-form { width: 100%; max-width: var(--dp-width-popover); }
.set-password-title { text-align: center; }
.set-password-note { display: flex; align-items: center; gap: var(--dp-space-2); margin: 0; color: var(--dp-text-muted); overflow-wrap: anywhere; }
.set-password-username { position: absolute; width: 1px; height: 1px; padding: 0; border: 0; overflow: hidden; clip-path: inset(50%); pointer-events: none; }
</style>
