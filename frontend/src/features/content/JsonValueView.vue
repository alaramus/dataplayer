<script setup lang="ts">
import { computed, ref } from "vue"

import { AppButton } from "@/shared/ui"

import type { JsonValue } from "./model"
import { quoted, scalarText } from "./model"

defineOptions({ name: "JsonValueView" })

const props = defineProps<{
  value: JsonValue
  label?: string
  depth?: number
}>()

const depth = computed(() => props.depth ?? 0)
const expanded = ref(depth.value < 2)
const visibleCount = ref(100)
const branch = computed(() => props.value.kind === "object" || props.value.kind === "array")
const count = computed(() => {
  if (props.value.kind === "object") return props.value.entries.length
  if (props.value.kind === "array") return props.value.items.length
  return 0
})
const objectEntries = computed(() =>
  props.value.kind === "object" ? props.value.entries.slice(0, visibleCount.value) : []
)
const arrayItems = computed(() =>
  props.value.kind === "array" ? props.value.items.slice(0, visibleCount.value) : []
)
const hasMore = computed(() => count.value > visibleCount.value)

function toggle() {
  if (branch.value) expanded.value = !expanded.value
}

function showMore() {
  visibleCount.value += 100
}
</script>

<template>
  <div class="json-value">
    <div v-if="value.kind === 'object' || value.kind === 'array'" class="json-value__branch">
      <div
        role="button"
        tabindex="0"
        class="json-value__summary"
        :aria-expanded="expanded"
        @click="toggle"
        @keydown.enter="toggle"
        @keydown.space.prevent="toggle"
      >
        <q-icon :name="expanded ? 'expand_more' : 'chevron_right'" />
        <span v-if="label !== undefined" class="json-value__key">{{ quoted(label) }}:</span>
        <span>{{ value.kind === "object" ? "{" : "[" }}</span>
        <span v-if="!expanded" class="json-value__count"
          >{{ count }} {{ count === 1 ? "item" : "items" }}</span
        >
      </div>

      <div v-if="expanded" class="json-value__children">
        <template v-if="value.kind === 'object'">
          <JsonValueView
            v-for="(entry, index) in objectEntries"
            :key="`${entry.name}:${index}`"
            :label="entry.name"
            :value="entry.value"
            :depth="depth + 1"
          />
        </template>
        <template v-else>
          <JsonValueView
            v-for="(item, index) in arrayItems"
            :key="index"
            :label="String(index)"
            :value="item"
            :depth="depth + 1"
          />
        </template>
        <AppButton
          v-if="hasMore"
          variant="quiet"
          size="sm"
          :label="`Show next ${Math.min(100, count - visibleCount)} items`"
          data-testid="json-show-more"
          @click="showMore"
        />
      </div>

      <div v-if="expanded" class="json-value__closing">
        {{ value.kind === "object" ? "}" : "]" }}
      </div>
    </div>

    <div v-else class="json-value__scalar">
      <span v-if="label !== undefined" class="json-value__key">{{ quoted(label) }}:</span>
      <span :class="`json-value__${value.kind}`">{{ scalarText(value) }}</span>
    </div>
  </div>
</template>

<style scoped>
.json-value {
  min-width: max-content;
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.65;
}
.json-value__summary,
.json-value__scalar {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-height: 20px;
}
.json-value__summary {
  cursor: pointer;
  user-select: none;
}
.json-value__summary:focus-visible {
  outline: 2px solid var(--dp-focus-border);
  outline-offset: -2px;
  border-radius: 3px;
}
.json-value__children {
  margin-left: 9px;
  padding-left: 13px;
  border-left: 1px solid var(--dp-border-faint);
}
.json-value__closing {
  margin-left: 20px;
}
.json-value__key {
  color: var(--dp-link);
}
.json-value__count,
.json-value__null {
  color: var(--dp-text-muted);
}
.json-value__string {
  color: var(--dp-text-strong);
}
.json-value__number,
.json-value__boolean {
  color: var(--dp-link);
}
</style>
