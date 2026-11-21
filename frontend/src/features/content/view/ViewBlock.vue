<script setup lang="ts">
import { t } from "@/shared/i18n"
import { AppBanner, stateTone } from "@/shared/ui"

import ViewPairs from "./ViewPairs.vue"
import ViewValue from "./ViewValue.vue"
import type { SectionChild, ViewBlock } from "./view"

/**
 * One block of a document's view (D420). The source says what is in it; how
 * it is laid out is decided here, the same for every source. A section draws
 * its children with this same component — sections do not nest, so that is
 * one level and no more.
 */
defineProps<{ block: ViewBlock | SectionChild }>()
const emit = defineEmits<{ open: [nodeId: string, label: string] }>()

function open(nodeId: string, label: string) {
  emit("open", nodeId, label)
}
</script>

<template>
  <details
    v-if="block.kind === 'section'"
    class="view-block view-block--section dp-disclosure"
    :open="block.collapsed !== true"
    data-testid="view-section"
  >
    <summary class="dp-section-title">
      {{ block.title }}
    </summary>
    <div class="view-block__children">
      <ViewBlock
        v-for="(child, index) in block.blocks"
        :key="index"
        :block="child"
        @open="open"
      />
    </div>
  </details>
  <dl
    v-else-if="block.kind === 'fields'"
    class="view-block view-block--fields"
    data-testid="view-fields"
  >
    <div
      v-for="(field, index) in block.fields"
      :key="index"
      class="view-block__field"
    >
      <dt class="view-block__label">
        {{ field.label }}
      </dt>
      <dd class="view-block__value">
        <ViewValue
          :value="field.value"
          @open="open"
        />
      </dd>
    </div>
  </dl>
  <ViewPairs
    v-else-if="block.kind === 'pairs'"
    class="view-block"
    :block="block"
    data-testid="view-pairs"
  />
  <div
    v-else-if="block.kind === 'table'"
    class="view-block view-block--table"
    data-testid="view-table"
  >
    <!-- An empty table keeps its columns: "None" alone under a field said
         nothing about what there was none of. -->
    <table class="view-block__table">
      <thead>
        <tr>
          <th
            v-for="column in block.columns"
            :key="column"
            scope="col"
          >
            {{ column }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, index) in block.rows"
          :key="index"
        >
          <td
            v-for="(value, column) in row"
            :key="column"
          >
            <ViewValue
              :value="value"
              @open="open"
            />
          </td>
        </tr>
        <tr v-if="block.rows.length === 0">
          <td
            class="view-block__none"
            :colspan="block.columns.length"
          >
            {{ t("content.view.nothing") }}
          </td>
        </tr>
      </tbody>
    </table>
    <p
      v-if="(block.omitted ?? 0) > 0"
      class="dp-meta"
    >
      {{ t("content.view.omitted", { n: block.omitted ?? 0 }) }}
    </p>
  </div>
  <AppBanner
    v-else-if="block.kind === 'notice'"
    class="view-block"
    :tone="stateTone(block.tone ?? 'neutral') ?? 'info'"
    data-testid="view-notice"
  >
    {{ block.text }}
  </AppBanner>
</template>

<style scoped>
.view-block--section > summary {
  padding: var(--dp-space-1) 0;
}
.view-block__children {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  padding: var(--dp-space-1) 0 var(--dp-space-2) var(--dp-space-5);
}
.view-block--fields {
  display: grid;
  grid-template-columns: minmax(auto, var(--dp-width-name)) 1fr;
  margin: 0;
}
.view-block__field {
  display: contents;
}
.view-block__label,
.view-block__value {
  padding: var(--dp-space-half) var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
}
.view-block__label {
  color: var(--dp-text-muted);
}
.view-block__value {
  margin: 0;
  min-width: 0;
}
.view-block--table {
  overflow-x: auto;
}
.view-block__table {
  border-collapse: collapse;
  min-width: 50%;
}
.view-block__table th {
  padding: var(--dp-space-half) var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border);
  color: var(--dp-text-muted);
  font-weight: 500;
  text-align: start;
}
.view-block__none {
  color: var(--dp-text-faint);
}
.view-block__table td {
  padding: var(--dp-space-half) var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
  vertical-align: top;
}
</style>
