<script setup lang="ts">
import { computed } from "vue"

import type { ConnectionCheckReport } from "@/client"
import { sourceFacts } from "@/features/connectors/sourceFacts"
import { copyText } from "@/shared/clipboard"
import { AppCopyButton, AppIconButton, useToast } from "@/shared/ui"

/**
 * What the last check said, in a panel over the button that ran it.
 *
 * A panel rather than a line in the form: the result is read once, acted on
 * and dismissed, and a line in the body pushed the fields about every time a
 * check was run. It sits above the button because that is where the eye is
 * when the answer arrives.
 *
 * What the source says it is goes here too, rather than in the connection's
 * Options where it used to live: "which server am I about to work on, and is
 * the extension there" is asked at the moment this button is pressed and at
 * no other. A draft nobody has saved answers it as well, because the check is
 * what asked.
 */
const props = defineProps<{
  result: ConnectionCheckReport | null
  /** What this kind of source is called, for the line naming its version. */
  sourceTitle: string
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
      <AppCopyButton
        tooltip="Copy the check result"
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
    <!-- What answered, under whether it answered at all. -->
    <dl
      v-if="facts.length"
      class="check-popover__facts"
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
            class="check-popover__note"
          >
            {{ fact.note }}
          </div>
        </dd>
      </template>
    </dl>
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
  z-index: var(--dp-layer-popover);
  padding: 12px 14px;
  border: 1px solid var(--dp-border-strong);
  border-radius: 6px;
  background: var(--dp-surface-raised);
  box-shadow: 0 4px 14px var(--dp-shadow-soft);
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
.check-popover__facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 12px;
  margin: 8px 0 0;
  padding-top: 8px;
  border-top: 1px solid var(--dp-border);
  font-size: 12px;
}
.check-popover__facts dt {
  color: var(--dp-text-muted);
}
.check-popover__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.check-popover__note {
  color: var(--dp-text-muted);
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
  border-top-color: var(--dp-border-strong);
}
.check-popover__tail::after {
  content: "";
  top: -9px;
  left: -8px;
  border-top-color: var(--dp-surface-raised);
}
</style>
