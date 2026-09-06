<script setup lang="ts">
import { computed } from "vue"

import {
  useRevealedCredentials,
  useServiceCredentials,
} from "@/features/services/api"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import { AppBanner, AppButton, AppCopyButton, AppSpinner, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * How to reach a service from outside this application, which is not the
 * address the connection beside it holds.
 *
 * One window in two situations, separated by the password. Opened by itself
 * the moment a service becomes usable, it hands the password over once, which
 * is what the warning above it is for. Opened later from the services window
 * it shows the address and the names and no secret, which is what makes that
 * one askable as often as anybody likes.
 */
const props = defineProps<{
  service: { id: string; name: string } | null
  /**
   * Whether this is that first moment. Decided by whoever opens the window
   * rather than by this component: only the screen that asked for a service
   * knows that one has just been made.
   */
  reveal?: boolean
}>()

const emit = defineEmits<{ "update:service": [value: null] }>()

const serviceId = computed(() => props.service?.id ?? null)
// Both are declared and one is enabled: which of the two answers this window
// is showing is a property of how it was opened, and a request that hands a
// password over must not be made by a window that was not opened to do it.
const revealing = computed(() => props.reveal === true)
const listening = computed(() => !revealing.value)
const shown = useServiceCredentials(serviceId, listening)
const handed = useRevealedCredentials(serviceId, revealing)

const answer = computed(() =>
  revealing.value ? handed.data.value : shown.data.value
)
const loading = computed(() =>
  revealing.value ? handed.isLoading.value : shown.isLoading.value
)
const failure = computed(() =>
  revealing.value ? handed.error.value : shown.error.value
)

const rows = computed(() => {
  const found = answer.value
  if (found === undefined) return []
  return [
    { label: "Host", value: found.host },
    { label: "Port", value: found.port === null ? null : String(found.port) },
    { label: "User", value: found.user },
    { label: "Database", value: found.database },
    // Only in the answer that carries one, and last of the parts, so it is
    // read after everything that says what it belongs to.
    { label: "Password", value: revealing.value ? handed.data.value?.password : null },
  ].filter((row): row is { label: string; value: string } => Boolean(row.value))
})

/**
 * What to say about the password.
 *
 * Four situations, and the one that matters is the first: a password this
 * server made up is being said for the only time it will ever be said, and a
 * person who closes this window without copying it has lost it. Said before
 * the rows rather than after them, because a warning under something the
 * reader has already closed is not a warning.
 */
const aboutThePassword = computed(() => {
  const mode = answer.value?.password_mode
  if (mode === "none") return "This service was started without a password."
  if (revealing.value) {
    if (mode === "chosen") return "It uses the password you typed for it."
    return (
      "This is the only time this password is shown. Copy it now — from here " +
      "on it lives encrypted in the connection and nothing can read it back."
    )
  }
  if (mode === "chosen") return "It uses the password you typed when you started it."
  return (
    "Its password was made up here and was shown once, when the service was " +
    "made. Start a service with a password of your own if you need to type " +
    "one in."
  )
})

/** Whether that sentence is a warning or a fact. */
const passwordTone = computed(() =>
  revealing.value && answer.value?.password_mode === "generated"
    ? "warning"
    : "info"
)

/**
 * The same thing as one line, which is what most tools actually take.
 *
 * Written by the server, because the grammar of an address belongs to the
 * source type that owns it: a screen that joined the parts itself would be a
 * second implementation of it, differing in the quoting first — putting a
 * password into one included. It carries the password in the answer that
 * hands one over and in no other, which is why this component does nothing
 * about it either way.
 */
const url = computed(() => answer.value?.url ?? null)

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
      <AppSpinner v-if="loading" />
      <AppBanner
        v-else-if="failure"
        tone="warning"
      >
        {{ messageOf(failure, "These could not be shown") }}
      </AppBanner>
      <template v-else>
        <!-- First of all, because it is the sentence that decides whether
             the reader has to do something before closing the window. -->
        <AppBanner
          :tone="passwordTone"
          data-testid="credential-password-note"
        >
          {{ aboutThePassword }}
        </AppBanner>
        <AppBanner
          v-if="answer?.unreachable_reason"
          tone="info"
        >
          {{ answer.unreachable_reason }}
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
             are what a form asks for, and this is what a terminal takes. In
             the one window that hands a password over it carries one, so this
             is the line to copy and keep. -->
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
