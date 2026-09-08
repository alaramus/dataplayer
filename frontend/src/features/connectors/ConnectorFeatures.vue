<script setup lang="ts">
import { toRef } from "vue"

import type { SourceFeature } from "@/client"
import { useSourceFeatures } from "@/features/connectors/features"
import { AppBanner, AppButton, AppSpinner } from "@/shared/ui"

const props = defineProps<{ connectorId: string }>()
const query = useSourceFeatures(toRef(props, "connectorId"))
const states: Record<SourceFeature["state"], string> = {
  available: "Available for inspection",
  absent: "Not installed",
  unsupported: "Unsupported inspection API",
  unavailable: "Inspection unavailable",
}
</script>

<template>
  <section
    v-if="query.isPending.value || query.isError.value || query.data.value?.features.length"
    aria-label="Detected source features"
    data-testid="connector-features"
  >
    <header class="connector-features__header">
      <h3>Detected source features</h3>
      <AppButton
        variant="secondary"
        size="sm"
        label="Reload"
        :loading="query.isFetching.value"
        data-testid="reload-source-features"
        @click="query.refetch()"
      />
    </header>
    <AppSpinner v-if="query.isPending.value" />
    <AppBanner
      v-else-if="query.isError.value"
      tone="info"
      data-testid="source-features-error"
    >
      Source features could not be inspected. Reload to try again.
    </AppBanner>
    <dl
      v-else
      class="connector-features__facts"
    >
      <template
        v-for="feature in query.data.value?.features"
        :key="feature.code"
      >
        <dt>{{ feature.title }}</dt>
        <dd :data-testid="`source-feature-${feature.code}`">
          <span v-if="feature.installed_version">{{ feature.installed_version }} — </span>
          {{ states[feature.state] }}
          <div v-if="feature.reason">
            {{ feature.reason }}
          </div>
        </dd>
      </template>
    </dl>
  </section>
</template>

<style scoped>
.connector-features__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.connector-features__header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.connector-features__facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 8px 16px;
  font-size: 12px;
}
.connector-features__facts dt {
  color: var(--dp-text-muted);
}
.connector-features__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
</style>
