<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ServerKey } from "@/client"
import { useServerKey } from "@/features/sshKeys/api"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppButton } from "@/shared/ui"

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

const describe = useServerKey()
const pinned = ref<ServerKey | null>(null)
const presented = ref<ServerKey | null>(null)
const matches = ref<boolean | null>(null)
const error = ref("")

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
      error.value = messageOf(cause, "The trusted key cannot be read")
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
    error.value = messageOf(cause, "The server could not be asked")
  }
}

function trust() {
  if (presented.value !== null) emit("update:modelValue", presented.value.public_key)
}
</script>

<template>
  <div
    class="server-key"
    data-testid="server-key"
  >
    <span class="server-key__label">Server key</span>
    <span
      v-if="pinned"
      class="server-key__line"
      data-testid="server-key-pinned"
    >
      Trusted: {{ pinned.algorithm }} {{ pinned.fingerprint }}
    </span>
    <span
      v-else
      class="server-key__line"
    >
      None trusted yet. Nothing connects until you fetch the server's key,
      compare it and trust it.
    </span>

    <div
      v-if="presented"
      class="server-key__presented"
      data-testid="server-key-presented"
    >
      <span class="server-key__line">
        The server presents: {{ presented.algorithm }} {{ presented.fingerprint }}
      </span>
      <span class="server-key__hint">
        Compare it with <code>ssh-keygen -lf</code> on its key in
        <code>/etc/ssh</code> on the server itself.
      </span>
      <AppBanner
        v-if="matches === false"
        tone="warning"
      >
        This is not the key trusted before. If the server was not reinstalled,
        somebody may be standing between you and it.
      </AppBanner>
      <span
        v-else-if="matches === true"
        class="server-key__line"
      >
        This is the key already trusted.
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
        label="Fetch from the server"
        :disable="disable || !hasAddress"
        :loading="describe.isPending.value"
        data-testid="server-key-fetch"
        @click="fetchPresented"
      />
      <AppButton
        v-if="presented && matches !== true"
        size="sm"
        :label="pinned ? 'Trust the new key' : 'Trust this key'"
        :disable="disable"
        data-testid="server-key-trust"
        @click="trust"
      />
    </div>
  </div>
</template>

<style scoped>
.server-key {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}
.server-key__label {
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
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
  color: var(--dp-text-muted);
}
.server-key__error {
  font-size: var(--dp-font-size-sm);
  color: var(--dp-content-error);
}
.server-key__buttons {
  display: flex;
  gap: var(--dp-space-2);
}
</style>
