<script setup lang="ts">
import { computed } from "vue"

import { useServiceCredentials } from "@/features/services/api"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import { AppBanner, AppButton, AppCopyButton, AppSpinner, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * How to reach a service from outside this application, shown once.
 *
 * The service is used through the connection beside it, and this application
 * never needs to say any of this out loud. It is here because the password
 * was made up by the server rather than chosen by the person who asked for
 * the database, and because somebody who starts a PostgreSQL usually wants to
 * point their own tools at it too.
 *
 * Once, and the window says so. It stays where every credential in this
 * application stays — encrypted in the connector — and there is no second way
 * to read it out (D4).
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
    { label: "Password", value: found.password },
  ].filter((row): row is { label: string; value: string } => Boolean(row.value))
})

/**
 * The same thing as one line, which is what most tools actually take.
 *
 * Written by the server, because the grammar of an address belongs to the
 * source type that owns it: a screen that joined the parts itself would be a
 * second implementation of it, differing in the quoting first. A type with no
 * address of its own answers with nothing, and then there is nothing to show.
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
    subtitle="Shown once. Copy anything you want to keep."
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
        <!-- Said before the password rather than after it: a warning under
             something a person has already closed the window on is not a
             warning. -->
        <AppBanner tone="warning">
          This password is not stored anywhere you can read it again. It lives
          encrypted in the connection from here on.
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
             are what a form asks for, and this is what a terminal takes. -->
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
