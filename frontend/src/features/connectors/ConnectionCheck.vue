<script setup lang="ts">
import { computed } from "vue"

import type { ConnectionCheckReport } from "@/client"
import { sourceFacts } from "@/features/connectors/sourceFacts"
import { copyText } from "@/shared/clipboard"
import { AppCopyButton, useToast } from "@/shared/ui"

const props = defineProps<{
  result: ConnectionCheckReport | null
  /** What this kind of source is called, for the line naming its version. */
  sourceTitle: string
}>()

const toast = useToast()

const KIND_LABELS: Record<string, string> = {
  auth: "Authentication failed",
  network: "Server unreachable",
  timeout: "Timed out",
  config: "Invalid parameters",
  locked: "Key locked",
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

/** What the source said about itself, where it said anything. */
const facts = computed(() => sourceFacts(props.result?.features, props.sourceTitle))

async function copy() {
  const said = facts.value.map((fact) => `${fact.label}: ${fact.value}`)
  await copyText([heading.value, ...lines.value, ...said].join("\n"))
  toast.success("Result copied")
}
</script>

<template>
  <div
    v-if="result"
    class="connection-check"
    :class="result.ok ? 'connection-check--ok' : 'connection-check--failed'"
    role="region"
    aria-label="Connection check result"
    data-testid="check-result"
  >
    <header class="connection-check__head">
      <span
        class="connection-check__heading"
        role="status"
        data-testid="check-heading"
      >
        {{ heading }}
      </span>
      <AppCopyButton
        tooltip="Copy the check result"
        data-testid="copy-check-result"
        @click="copy"
      />
    </header>
    <div
      class="connection-check__details"
      tabindex="0"
      aria-label="Check details"
    >
      <p
        v-for="line in lines"
        :key="line"
        class="connection-check__line"
      >
        {{ line }}
      </p>
      <!-- What answered, under whether it answered at all. -->
      <dl
        v-if="facts.length"
        class="connection-check__facts"
        data-testid="check-source-facts"
      >
        <template
          v-for="fact in facts"
          :key="fact.code"
        >
          <dt>{{ fact.label }}</dt>
          <dd :data-testid="`source-fact-${fact.code}`">
            {{ fact.value }}
            <div
              v-if="fact.note"
              class="connection-check__note"
            >
              {{ fact.note }}
            </div>
          </dd>
        </template>
      </dl>
    </div>
    <!-- The one way on from what the check said, beside the saying of it —
         in the strip of buttons below it pushed every other one about. -->
    <div
      v-if="$slots.action"
      class="connection-check__action"
    >
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
.connection-check {
  display: flex;
  flex-direction: column;
  width: min(420px, calc(100vw - var(--dp-space-5)));
  max-height: min(var(--dp-operation-result-height), calc(100dvh - var(--dp-space-4)));
  min-height: 0;
  padding: var(--dp-space-2) var(--dp-space-4);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
  background: var(--dp-surface-raised);
}
.connection-check__details {
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
}
.connection-check__details:focus-visible {
  outline: 2px solid var(--dp-focus-border);
  outline-offset: calc(-1 * var(--dp-space-half));
}
.connection-check__head {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  margin-bottom: var(--dp-space-2);
}
.connection-check__heading {
  flex: 1;
  font-weight: 600;
}
.connection-check--ok .connection-check__heading {
  color: var(--dp-content-success);
}
.connection-check--failed .connection-check__heading {
  color: var(--dp-content-error);
}
.connection-check__line {
  margin: 0;
  font-size: var(--dp-font-size);
  overflow-wrap: anywhere;
}
.connection-check__facts {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
  gap: var(--dp-space-1) var(--dp-space-3);
  margin: var(--dp-space-2) 0 0;
  padding-top: var(--dp-space-2);
  border-top: 1px solid var(--dp-border);
  font-size: var(--dp-font-size-sm);
}
.connection-check__facts dt {
  overflow-wrap: anywhere;
  color: var(--dp-text-muted);
}
.connection-check__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.connection-check__note {
  color: var(--dp-text-muted);
}
.connection-check__action {
  flex: none;
  display: flex;
  margin-top: var(--dp-space-2);
}
</style>
