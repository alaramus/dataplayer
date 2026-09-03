<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ServiceTemplateInfo } from "@/client"
import { buildStart, canStart } from "@/features/services/starts"
import type { StartForm, StartRequest } from "@/features/services/starts"
import { AppButton, AppCheckbox, AppInput, AppSelect } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * Two ways to start a database here, and the difference between them is how
 * many questions get asked.
 *
 * Automatic asks none — not even the name. It is the demonstration: one press
 * and a server appears, filled with something to look at and reachable from
 * the machine, with a password this server made up and shows once. Somebody
 * who has not been asked for a name has not got one in mind, and asking for
 * one is the difference between a demonstration and a form.
 *
 * Chosen asks for what is a person's to decide, and nothing else. What runs
 * is still the template's — no image, no command, no path, no port number
 * (D80) — and the password is still the server's, because a chosen one would
 * have to be written down somewhere between the request and the job that uses
 * it (D4).
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
const publish = ref(true)
const sampleData = ref(true)

/** Which credentials this template lets a person name, in the server's order. */
const asksFor = computed(() => props.template?.choosable ?? [])
const offersSampleData = computed(() => props.template?.offers_sample_data ?? false)

// Opened on a template, it starts over: the last service somebody made is not
// a draft of the next one.
watch(
  () => props.template,
  (template) => {
    mode.value = "automatic"
    name.value = template?.title ?? ""
    user.value = ""
    database.value = ""
    publish.value = true
    sampleData.value = template?.offers_sample_data ?? false
  }
)

/** What has been filled in, as the plain object `starts.ts` reasons about. */
const form = computed<StartForm>(() => ({
  mode: mode.value,
  name: name.value,
  user: user.value,
  database: database.value,
  publish: publish.value,
  sampleData: sampleData.value,
  choosable: asksFor.value,
  offersSampleData: offersSampleData.value,
}))

const ready = computed(() => canStart(form.value))

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
        connection for you, and gives it a password nobody has to choose. You
        will be shown how to reach it from your own tools once — and only once.
        <template v-if="offersSampleData">
          It comes with a sample schema, so there is something to look at.
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
        <AppCheckbox
          v-model="publish"
          label="Reachable from this machine, on a port picked for it"
          data-testid="service-publish"
        />
        <AppCheckbox
          v-if="offersSampleData"
          v-model="sampleData"
          label="Put a sample schema in it"
          data-testid="service-sample-data"
        />
        <p class="start-service__what">
          Runs <code>{{ template?.image }}</code> on this server. The password
          is made up here either way and shown to you once.
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
