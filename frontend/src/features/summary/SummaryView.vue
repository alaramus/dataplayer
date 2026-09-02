<script setup lang="ts">
import { computed, toRef } from "vue"

import { useNodeSummary } from "@/features/summary/api"
import { describe } from "@/features/summary/facts"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppSection, AppSpinner } from "@/shared/ui"

/**
 * What one node is: its own facts, and what its format states about itself.
 *
 * Everything shown here was decided by the source (D75). This screen chooses
 * the order of the lines and nothing else — which is why the whole of it is
 * one call to a pure function, tested beside it without mounting anything.
 */
const props = defineProps<{ connectorId: string; nodeId: string }>()
const connectorId = toRef(props, "connectorId")
const nodeId = toRef(props, "nodeId")
const query = useNodeSummary(connectorId, nodeId)

defineExpose({ reload: async () => void (await query.refetch()) })

const described = computed(() =>
  query.data.value === undefined ? null : describe(query.data.value)
)
const errorText = computed(() =>
  query.error.value === null
    ? ""
    : messageOf(query.error.value, "Could not read this node")
)
</script>

<template>
  <div
    class="summary-view"
    data-testid="summary-view"
  >
    <AppBanner
      v-if="errorText"
      tone="error"
      data-testid="summary-error"
    >
      {{ errorText }}
    </AppBanner>

    <AppSpinner v-else-if="query.isPending.value" />

    <template v-else-if="described !== null && query.data.value">
      <AppSection data-testid="summary-facts">
        <div class="summary-view__title">
          {{ query.data.value.name }}
        </div>
        <dl class="summary-view__facts">
          <template
            v-for="fact in described.facts"
            :key="fact.label"
          >
            <dt>{{ fact.label }}</dt>
            <dd :data-testid="`summary-fact-${fact.label}`">
              {{ fact.value }}
            </dd>
          </template>
        </dl>
      </AppSection>

      <AppSection
        v-if="described.contents.length > 0"
        divided
        data-testid="summary-contents"
      >
        <div class="summary-view__title">
          Contents
        </div>
        <dl class="summary-view__facts">
          <template
            v-for="fact in described.contents"
            :key="fact.label"
          >
            <dt>{{ fact.label }}</dt>
            <dd :data-testid="`summary-fact-${fact.label}`">
              {{ fact.value }}
            </dd>
          </template>
        </dl>
      </AppSection>

      <!-- What the source could not say, and why: bytes that are not the
           format their name promised, or a count that hit its ceiling. -->
      <AppSection
        v-if="described.notice"
        divided
      >
        <AppBanner
          tone="info"
          data-testid="summary-notice"
        >
          {{ described.notice }}
        </AppBanner>
      </AppSection>
    </template>
  </div>
</template>

<style scoped>
.summary-view {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
}
.summary-view__title {
  font-weight: 600;
  margin-bottom: 8px;
}
.summary-view__facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 16px;
  margin: 0;
  font-size: 12px;
}
.summary-view__facts dt {
  color: var(--dp-text-muted);
}
.summary-view__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
</style>
