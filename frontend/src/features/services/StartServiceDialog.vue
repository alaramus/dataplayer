<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ServiceTemplateInfo } from "@/client"
import { buildStart, canStart, passwordProblem } from "@/features/services/starts"
import type { StartForm, StartRequest } from "@/features/services/starts"
import { useSshKeys } from "@/features/sshKeys/api"
import { keyChoiceLabel } from "@/features/sshKeys/keys"
import { t } from "@/shared/i18n"
import {
  AppButton,
  AppCheckbox,
  AppForm,
  AppInput,
  AppNumberInput,
  AppSelect,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * Two ways to start a database, differing in how many questions are asked.
 *
 * Automatic asks none, not even the name: somebody who has not been asked for
 * a name has not got one in mind, and asking is the difference between a
 * demonstration and a form. Chosen asks what is a person's to decide — the
 * name, the names inside it, the port and the password. What runs is the
 * template's either way: no image, no command, no path (D80).
 */
const props = defineProps<{
  template: ServiceTemplateInfo | null
}>()

const emit = defineEmits<{
  "update:template": [value: ServiceTemplateInfo | null]
  start: [payload: { templateKey: string; start: StartRequest; label: string }]
}>()

const mode = ref<"automatic" | "chosen">("automatic")
const name = ref("")
const user = ref("")
const database = ref("")
// Zero rather than empty: the server takes it to mean "pick a free one", and
// a field that starts empty asks a question nobody has to answer.
const port = ref<number | null>(0)
const wantsPassword = ref(true)
const password = ref("")
const signIn = ref<"password" | "key">("password")
const keyId = ref("")
const sampleData = ref(true)

/** Which credentials this template lets a person name, in the server's order. */
const asksFor = computed(() => props.template?.choosable ?? [])
const offersSampleData = computed(() => props.template?.offers_sample_data ?? false)
const optionalPassword = computed(() => props.template?.optional_password ?? false)
/** Whether this one may be signed into with the person's own key (D154). */
const keySignIn = computed(() => props.template?.key_sign_in ?? false)
const withKey = computed(() => keySignIn.value && signIn.value === "key")
// Asked for only where a key is on offer, so a PostgreSQL form reads nothing.
const sshKeys = useSshKeys(computed(() => keySignIn.value && mode.value === "chosen"))
const keyChoices = computed(() =>
  (sshKeys.data.value ?? []).map((key) => ({ label: keyChoiceLabel(key), value: key.id }))
)
const signIns = computed(() => [
  { label: t("services.start.sign_in_password"), value: "password" },
  { label: t("services.start.sign_in_key"), value: "key" },
])

// Opened on a template, it starts over: the last service somebody made is not
// a draft of the next one.
watch(
  () => props.template,
  (template) => {
    mode.value = "automatic"
    name.value = template?.title ?? ""
    user.value = ""
    database.value = ""
    port.value = 0
    wantsPassword.value = true
    password.value = ""
    signIn.value = "password"
    keyId.value = ""
    sampleData.value = template?.offers_sample_data ?? false
  }
)

/** What has been filled in, as the plain object `starts.ts` reasons about. */
const form = computed<StartForm>(() => ({
  mode: mode.value,
  name: name.value,
  user: user.value,
  database: database.value,
  port: port.value ?? 0,
  wantsPassword: wantsPassword.value,
  password: password.value,
  signIn: signIn.value,
  keyId: keyId.value,
  sampleData: sampleData.value,
  choosable: asksFor.value,
  offersSampleData: offersSampleData.value,
  optionalPassword: optionalPassword.value,
  keySignIn: keySignIn.value,
}))

const ready = computed(() => canStart(form.value))
const passwordSays = computed(() => passwordProblem(form.value) ?? "")

function start() {
  const template = props.template
  if (!template || !ready.value) return
  const request: StartRequest = buildStart(form.value)
  emit("start", {
    templateKey: template.key,
    start: request,
    label: mode.value === "automatic" ? template.title : name.value.trim(),
  })
  emit("update:template", null)
}

const modes = computed(() => [
  { label: t("services.start.automatic"), value: "automatic" },
  { label: t("services.start.chosen"), value: "chosen" },
])
</script>

<template>
  <WindowDialog
    :model-value="template !== null"
    size="long-form"
    sizing="stable"
    :title="t('services.start.title', { name: template?.title ?? '' })"
    :subtitle="t('services.start.subtitle')"
    data-testid="start-service-dialog"
    @update:model-value="emit('update:template', null)"
  >
    <AppForm layout="section">
      <AppSelect
        v-model="mode"
        :label="t('services.start.how')"
        :options="modes"
        data-testid="service-mode"
      />

      <p
        v-if="mode === 'automatic'"
        class="start-service__what"
        data-testid="service-automatic-summary"
      >
        {{ t('services.start.runs') }} <code>{{ template?.image }}</code>
        {{ t('services.start.automatic_rest') }}
        <template v-if="offersSampleData">
          {{ t('services.start.sample_note') }}
        </template>
      </p>

      <template v-else>
        <AppInput
          v-model="name"
          :label="t('services.start.name')"
          autocomplete="off"
          data-testid="service-name"
          @keydown.enter="start"
        />
        <AppInput
          v-if="asksFor.includes('user')"
          v-model="user"
          :label="t('services.start.user')"
          :placeholder="t('services.start.optional')"
          autocomplete="off"
          data-testid="service-user"
        />
        <AppInput
          v-if="asksFor.includes('database')"
          v-model="database"
          :label="t('services.start.database')"
          :placeholder="t('services.start.optional')"
          autocomplete="off"
          data-testid="service-database"
        />
        <AppNumberInput
          v-model="port"
          :label="t('services.start.port')"
          :hint="t('services.start.port_hint')"
          data-testid="service-port"
        />
        <!-- Only where running without one is a configuration rather than a
             mistake. A PostgreSQL that trusts every connection is not a
             service this server will start, so it is never offered. -->
        <AppCheckbox
          v-if="optionalPassword"
          v-model="wantsPassword"
          :label="t('services.start.ask_password')"
          data-testid="service-wants-password"
        />
        <!-- A server one signs into, rather than a database: its owner's own
             key may open it instead of a password (D154). -->
        <AppSelect
          v-if="keySignIn"
          v-model="signIn"
          :label="t('services.start.sign_in')"
          :options="signIns"
          data-testid="service-sign-in"
        />
        <AppSelect
          v-if="withKey"
          v-model="keyId"
          :label="t('services.start.your_key')"
          :options="keyChoices"
          :hint="
            keyChoices.length === 0
              ? t('services.start.no_keys')
              : t('services.start.key_hint')
          "
          data-testid="service-key"
        />
        <AppInput
          v-if="!withKey && asksFor.includes('password') && (wantsPassword || !optionalPassword)"
          v-model="password"
          type="password"
          :label="t('services.start.password')"
          :hint="t('services.start.password_hint')"
          :error="passwordSays"
          autocomplete="new-password"
          data-testid="service-password"
        />
        <AppCheckbox
          v-if="offersSampleData"
          v-model="sampleData"
          :label="t('services.start.sample')"
          data-testid="service-sample-data"
        />
        <p class="start-service__what">
          {{ t('services.start.runs') }} <code>{{ template?.image }}</code>
          {{ t('services.start.chosen_rest') }}
          <template v-if="withKey">
            {{ t('services.start.key_note') }}
          </template>
          <template v-else>
            {{ t('services.start.password_note') }}
          </template>
        </p>
      </template>
    </AppForm>

    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        @click="emit('update:template', null)"
      />
      <AppButton
        :label="t('services.start.start')"
        :disable="!ready"
        data-testid="start-service-confirm"
        @click="start"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.start-service__what {
  margin: 0;
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
}
</style>
