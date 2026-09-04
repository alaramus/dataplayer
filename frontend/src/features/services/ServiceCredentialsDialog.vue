<script setup lang="ts">
import { computed } from "vue"

import { useServiceCredentials } from "@/features/services/api"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import { AppBanner, AppButton, AppCopyButton, AppSpinner, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * How to reach a service from outside this application, whenever it is asked.
 *
 * The service is used through the connection beside it, and this application
 * never needs any of this. It is here because somebody who starts a
 * PostgreSQL usually wants to point their own tools at it too, and the
 * address it answers on for them is not the one the connection holds.
 *
 * Never the password. It stays where every credential in this application
 * stays — encrypted in the connector (D4) — and that is what makes the rest
 * of it something a person can be told again tomorrow.
 */
const props = defineProps<{
  service: { id: string; name: string } | null
}>()

const emit = defineEmits<{ "update:service": [value: null] }>()

const serviceId = computed(() => props.service?.id ?? null)
const credentials = useServiceCredentials(serviceId)

const rows = computed(() => {
  const found = credentials.data.value
  if (found === undefined) return []
  return [
    { label: "Host", value: found.host },
    { label: "Port", value: found.port === null ? null : String(found.port) },
    { label: "User", value: found.user },
    { label: "Database", value: found.database },
  ].filter((row): row is { label: string; value: string } => Boolean(row.value))
})

/**
 * What to say about the password, which is never one of the rows above.
 *
 * Three different things rather than one: one somebody typed is one they
 * already know, one this server made up is gone for good, and a service that
 * wants none has nothing to say at all.
 */
const aboutThePassword = computed(() => {
  switch (credentials.data.value?.password_mode) {
    case "chosen":
      return "It uses the password you typed when you started it."
    case "none":
      return "This service was started without a password."
    default:
      return (
        "Its password was made up here and is not shown anywhere. Start a " +
        "service with a password of your own if you need to type one in."
      )
  }
})

/**
 * The same thing as one line, which is what most tools actually take.
 *
 * Written by the server, because the grammar of an address belongs to the
 * source type that owns it: a screen that joined the parts itself would be a
 * second implementation of it, differing in the quoting first. A type with no
 * address of its own answers with nothing, and then there is nothing to show.
 * Without the password, so it is a line that can be pasted anywhere.
 */
const url = computed(() => credentials.data.value?.url ?? null)

const toast = useToast()

async function copy(what: string, said: string) {
  await copyText(what)
  toast.success(said)
}
</script>

<template>
  <WindowDialog
    :model-value="service !== null"
    size="md"
    :title="`Connecting to ${service?.name ?? ''}`"
    subtitle="Where this service answers, for your own tools."
    data-testid="service-credentials-dialog"
    @update:model-value="emit('update:service', null)"
  >
    <div class="credentials">
      <AppSpinner v-if="credentials.isLoading.value" />
      <AppBanner
        v-else-if="credentials.isError.value"
        tone="warning"
      >
        {{ messageOf(credentials.error.value, "These could not be shown") }}
      </AppBanner>
      <template v-else>
        <!-- What is not on the list, said where somebody looking for it will
             read it rather than after they have closed the window. -->
        <AppBanner
          tone="info"
          data-testid="credential-password-note"
        >
          {{ aboutThePassword }}
        </AppBanner>
        <AppBanner
          v-if="credentials.data.value?.unreachable_reason"
          tone="info"
        >
          {{ credentials.data.value.unreachable_reason }}
        </AppBanner>
        <div
          v-for="row in rows"
          :key="row.label"
          class="credentials__row"
          :data-testid="`credential-${row.label.toLowerCase()}`"
        >
          <span class="credentials__label">{{ row.label }}</span>
          <code class="credentials__value">{{ row.value }}</code>
          <AppCopyButton
            :tooltip="`Copy the ${row.label.toLowerCase()}`"
            :data-testid="`copy-${row.label.toLowerCase()}`"
            @click="copy(row.value, `${row.label} copied`)"
          />
        </div>

        <!-- Last, and the one most people will actually use: the parts above
             are what a form asks for, and this is what a terminal takes. The
             password is not in it, like every other address this application
             shows. -->
        <div
          v-if="url"
          class="credentials__row"
          data-testid="credential-url"
        >
          <span class="credentials__label">URL</span>
          <code class="credentials__value">{{ url }}</code>
          <AppCopyButton
            tooltip="Copy the connection string"
            data-testid="copy-url"
            @click="copy(url, 'Connection string copied')"
          />
        </div>
      </template>
    </div>

    <template #actions>
      <AppButton
        label="Done"
        data-testid="credentials-done"
        @click="emit('update:service', null)"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.credentials {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.credentials__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: var(--dp-radius-control);
  background: var(--dp-surface-raised);
}
.credentials__label {
  font-size: 11px;
  color: var(--dp-text-muted);
  width: 70px;
  flex: none;
}
.credentials__value {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  white-space: nowrap;
  font-size: 12px;
}
</style>
