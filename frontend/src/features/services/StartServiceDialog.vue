<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ServiceTemplateInfo } from "@/client"
import { buildStart, canStart, passwordProblem } from "@/features/services/starts"
import type { StartForm, StartRequest } from "@/features/services/starts"
import {
  AppButton,
  AppCheckbox,
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
const sampleData = ref(true)

/** Which credentials this template lets a person name, in the server's order. */
const asksFor = computed(() => props.template?.choosable ?? [])
const offersSampleData = computed(() => props.template?.offers_sample_data ?? false)
const optionalPassword = computed(() => props.template?.optional_password ?? false)

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
  sampleData: sampleData.value,
  choosable: asksFor.value,
  offersSampleData: offersSampleData.value,
  optionalPassword: optionalPassword.value,
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

const modes = [
  { label: "Set it up for me", value: "automatic" },
  { label: "Let me choose", value: "chosen" },
]
</script>

<template>
  <WindowDialog
    :model-value="template !== null"
    size="lg"
    :title="`Start ${template?.title ?? ''} here`"
    subtitle="This server runs it and saves the connection for you."
    data-testid="start-service-dialog"
    @update:model-value="emit('update:template', null)"
  >
    <div class="start-service">
      <AppSelect
        v-model="mode"
        label="How"
        :options="modes"
        data-testid="service-mode"
      />

      <p
        v-if="mode === 'automatic'"
        class="start-service__what"
        data-testid="service-automatic-summary"
      >
        Runs <code>{{ template?.image }}</code> on this server, names the
        connection for you, and gives it a password nobody has to choose. It
        will tell you where to reach it from your own tools.
        <template v-if="offersSampleData">
          It comes filled with sample data, so there is something to look at.
        </template>
      </p>

      <template v-else>
        <AppInput
          v-model="name"
          label="Name this connection"
          data-testid="service-name"
          @keydown.enter="start"
        />
        <AppInput
          v-if="asksFor.includes('user')"
          v-model="user"
          label="Role to create (optional)"
          data-testid="service-user"
        />
        <AppInput
          v-if="asksFor.includes('database')"
          v-model="database"
          label="Database to create (optional)"
          data-testid="service-database"
        />
        <AppNumberInput
          v-model="port"
          label="Port on this machine"
          hint="0 lets this server pick a free one"
          data-testid="service-port"
        />
        <!-- Only where running without one is a configuration rather than a
             mistake. A PostgreSQL that trusts every connection is not a
             service this server will start, so it is never offered. -->
        <AppCheckbox
          v-if="optionalPassword"
          v-model="wantsPassword"
          label="Ask for a password"
          data-testid="service-wants-password"
        />
        <AppInput
          v-if="asksFor.includes('password') && (wantsPassword || !optionalPassword)"
          v-model="password"
          type="password"
          label="Password"
          hint="Leave it empty and one is made up here"
          :error="passwordSays"
          data-testid="service-password"
        />
        <AppCheckbox
          v-if="offersSampleData"
          v-model="sampleData"
          label="Fill it with sample data"
          data-testid="service-sample-data"
        />
        <p class="start-service__what">
          Runs <code>{{ template?.image }}</code> on this server, reachable
          from this machine and from nowhere else. A password made up here is
          never shown afterwards, so type one if you mean to use it elsewhere.
        </p>
      </template>
    </div>

    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('update:template', null)"
      />
      <AppButton
        label="Start"
        :disable="!ready"
        data-testid="start-service-confirm"
        @click="start"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.start-service {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 2px;
}
.start-service__what {
  margin: 0;
  font-size: 12px;
  color: var(--dp-text-muted);
}
</style>
