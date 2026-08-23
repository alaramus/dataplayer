<script setup lang="ts">
import { computed } from "vue"

import type { ConnectionCheckResult } from "@/client"
import { AppButton, AppIconButton, useToast } from "@/shared/ui"

/**
 * What the last check said, in a panel over the button that ran it.
 *
 * A panel rather than a line in the form: the result is read once, acted on
 * and dismissed, and a line in the body pushed the fields about every time a
 * check was run. It sits above the button because that is where the eye is
 * when the answer arrives.
 */
const props = defineProps<{
  result: ConnectionCheckResult | null
}>()

const emit = defineEmits<{ close: [] }>()

const toast = useToast()

const KIND_LABELS: Record<string, string> = {
  auth: "Authentication failed",
  network: "Server unreachable",
  timeout: "Timed out",
  config: "Invalid parameters",
  unknown: "Unknown error",
}

const heading = computed(() => (props.result?.ok === true ? "Succeeded" : "Failed"))

/** The lines of the answer, each already safe to show — see AdapterError. */
const lines = computed(() => {
  const result = props.result
  if (!result) return []
  const collected: string[] = []
  if (!result.ok) {
    const kind = result.error_kind
    if (kind && KIND_LABELS[kind]) collected.push(KIND_LABELS[kind])
  }
  collected.push(result.message)
  if (result.latency_ms !== null && result.latency_ms !== undefined) {
    collected.push(`Ping: ${String(result.latency_ms)} ms`)
  }
  return collected
})

async function copy() {
  await navigator.clipboard.writeText([heading.value, ...lines.value].join("\n"))
  toast.success("Result copied")
}
</script>

<template>
  <div
    v-if="result"
    class="check-popover"
    :class="result.ok ? 'check-popover--ok' : 'check-popover--failed'"
    data-testid="check-result"
  >
    <header class="check-popover__head">
      <span
        class="check-popover__heading"
        data-testid="check-heading"
      >
        {{ heading }}
      </span>
      <AppButton
        variant="quiet"
        label="Copy"
        data-testid="copy-check-result"
        @click="copy"
      />
      <AppIconButton
        icon="close"
        tooltip="Dismiss this result"
        data-testid="dismiss-check-result"
        @click="emit('close')"
      />
    </header>
    <p
      v-for="line in lines"
      :key="line"
      class="check-popover__line"
    >
      {{ line }}
    </p>
    <!-- The tail that points at the button below, as in a speech bubble: what
         makes the panel belong to that button rather than float over the
         form. -->
    <span class="check-popover__tail" />
  </div>
</template>

<style scoped>
.check-popover {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: calc(100% + 10px);
  z-index: 1;
  padding: 12px 14px;
  border: 1px solid rgba(128, 128, 128, 0.4);
  border-radius: 6px;
  background: var(--q-page-background, #fff);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.18);
}
.check-popover__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.check-popover__heading {
  flex: 1;
  font-weight: 600;
}
.check-popover--ok .check-popover__heading {
  color: var(--q-positive);
}
.check-popover--failed .check-popover__heading {
  color: var(--q-negative);
}
.check-popover__line {
  margin: 0;
  font-size: 13px;
  overflow-wrap: anywhere;
}
/* Two triangles, the back one a pixel lower, so the border of the panel
   appears to continue around the tail. */
.check-popover__tail,
.check-popover__tail::after {
  position: absolute;
  top: 100%;
  left: 28px;
  width: 0;
  height: 0;
  border: 8px solid transparent;
  border-bottom: none;
  border-top-color: rgba(128, 128, 128, 0.4);
}
.check-popover__tail::after {
  content: "";
  top: -9px;
  left: -8px;
  border-top-color: var(--q-page-background, #fff);
}
</style>
