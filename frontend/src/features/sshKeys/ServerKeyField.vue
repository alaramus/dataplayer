<script setup lang="ts">
import { computed, inject, ref, watch } from "vue"

import type { ServerKey } from "@/client"
import { useServerKey } from "@/features/sshKeys/api"
import { codeParts, codePlaces } from "@/features/sshKeys/keys"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppBanner, AppButton } from "@/shared/ui"
import { formLayoutKey } from "@/shared/ui/formLayout"

/**
 * The key a server proves itself with, trusted by a person rather than typed
 * (D145).
 *
 * What is trusted is described as it opens; the server is asked only when
 * the button says so, and asking sends a greeting and nothing else. Trusting
 * is a press of its own after the fingerprint is on screen, so that nobody
 * trusts a key they have not been shown. Every comparison is the server's.
 */
const props = defineProps<{
  adapterType: string
  /** What the form holds now: the address comes from here. */
  options: Record<string, unknown>
  /** The trusted key as one `known_hosts` line, or empty. */
  modelValue: string
  disable: boolean
}>()
const emit = defineEmits<{ "update:modelValue": [value: string] }>()

const formLayout = inject(formLayoutKey, false)
const describe = useServerKey()
const pinned = ref<ServerKey | null>(null)
const presented = ref<ServerKey | null>(null)
const matches = ref<boolean | null>(null)
const error = ref("")

const COMPARE_CODES = { command: "ssh-keygen -lf", folder: "/etc/ssh" }
const compareParts = computed(() =>
  codeParts(t("ssh_keys.server_key.compare", codePlaces(COMPARE_CODES)), COMPARE_CODES)
)

const hasAddress = computed(
  () => typeof props.options.host === "string" && props.options.host.trim() !== ""
)

// What is trusted, said again whenever it changes — from a press here, or
// from a connection being loaded into the window.
watch(
  () => props.modelValue,
  async (line) => {
    presented.value = null
    matches.value = null
    if (line.trim() === "") {
      pinned.value = null
      return
    }
    try {
      const report = await describe.mutateAsync({
        adapter_type: props.adapterType,
        options: { host_key: line },
      })
      pinned.value = report.pinned
    } catch (cause) {
      error.value = messageOf(cause, t("ssh_keys.server_key.unreadable"))
    }
  },
  { immediate: true }
)

async function fetchPresented() {
  error.value = ""
  try {
    const report = await describe.mutateAsync({
      adapter_type: props.adapterType,
      options: { ...props.options, host_key: props.modelValue },
      fetch: true,
    })
    presented.value = report.presented ?? null
    matches.value = report.matches ?? null
  } catch (cause) {
    error.value = messageOf(cause, t("ssh_keys.server_key.not_asked"))
  }
}

function trust() {
  if (presented.value !== null) emit("update:modelValue", presented.value.public_key)
}
</script>

<template>
  <div
    class="server-key"
    :class="{ 'server-key--form': formLayout }"
    data-testid="server-key"
  >
    <span class="server-key__label">{{ t('ssh_keys.server_key.label') }}</span>
    <div class="server-key__body">
      <span
        v-if="pinned"
        class="server-key__line"
        data-testid="server-key-pinned"
      >
        {{ t('ssh_keys.server_key.trusted', { algorithm: pinned.algorithm, fingerprint: pinned.fingerprint }) }}
      </span>
      <span
        v-else
        class="server-key__line"
      >
        {{ t('ssh_keys.server_key.none') }}
      </span>

      <div
        v-if="presented"
        class="server-key__presented"
        data-testid="server-key-presented"
      >
        <span class="server-key__line">
          {{ t('ssh_keys.server_key.presents', { algorithm: presented.algorithm, fingerprint: presented.fingerprint }) }}
        </span>
        <span class="server-key__hint">
          <template
            v-for="(part, index) in compareParts"
            :key="index"
          >
            <code v-if="part.code">{{ part.text }}</code>
            <span v-else>{{ part.text }}</span>
          </template>
        </span>
        <AppBanner
          v-if="matches === false"
          tone="warning"
        >
          {{ t('ssh_keys.server_key.changed') }}
        </AppBanner>
        <span
          v-else-if="matches === true"
          class="server-key__line"
        >
          {{ t('ssh_keys.server_key.same') }}
        </span>
      </div>

      <span
        v-if="error"
        class="server-key__error"
      >{{ error }}</span>

      <div class="server-key__buttons">
        <AppButton
          variant="secondary"
          size="sm"
          :label="t('ssh_keys.server_key.fetch')"
          :disable="disable || !hasAddress"
          :loading="describe.isPending.value"
          data-testid="server-key-fetch"
          @click="fetchPresented"
        />
        <AppButton
          v-if="presented && matches !== true"
          size="sm"
          :label="pinned ? t('ssh_keys.server_key.trust_new') : t('ssh_keys.server_key.trust')"
          :disable="disable"
          data-testid="server-key-trust"
          @click="trust"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.server-key,
.server-key__body {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  min-width: 0;
}
/* In a form the key stands in the label and control columns like every
   field beside it; it was a 12px grey heading over a block the form's full
   width, the one row of the SSH form that did not line up. */
.server-key--form {
  display: grid;
  grid-template-columns: var(--dp-form-label-width) minmax(0, 1fr);
  column-gap: 0;
}
@container app-form (max-width: 480px) {
  .server-key--form {
    display: flex;
  }
}
.server-key__label {
  font-size: var(--dp-font-size);
  line-height: var(--dp-line-height);
}
.server-key__line {
  line-height: var(--dp-line-height);
}
.server-key__line {
  font-size: var(--dp-font-size);
  overflow-wrap: anywhere;
}
.server-key__presented {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}
.server-key__hint {
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
  color: var(--dp-text-muted);
}
.server-key__error {
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
  color: var(--dp-content-error);
}
.server-key__buttons {
  display: flex;
  gap: var(--dp-space-2);
}
</style>
