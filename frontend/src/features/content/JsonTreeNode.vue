<script setup lang="ts">
import { computed, ref } from "vue"

import { childrenOf, closedSummary, scalarOf } from "@/features/content/jsonTree"
import type { JsonValue } from "@/features/content/jsonTree"
import { appIcons } from "@/shared/ui"

/**
 * One value of a JSON tree, and what is inside it when it is opened (D295).
 *
 * Read only. Objects and arrays open one level at a time; the levels a
 * caller asks for are open from the start.
 */
const props = withDefaults(
  defineProps<{
    value: JsonValue
    name?: string | null
    depth?: number
    /** How many levels are open when the tree is first drawn. */
    openLevels?: number
    /** The whole value: its children are drawn, not a line of its own. */
    root?: boolean
  }>(),
  { name: null, depth: 0, openLevels: 1, root: false }
)

const scalar = computed(() => scalarOf(props.value))
const children = computed(() => childrenOf(props.value))
const open = ref(props.root || props.depth < props.openLevels)
</script>

<template>
  <div class="json-node">
    <div
      v-if="!(root && scalar === null)"
      class="json-node__line"
      :style="{ paddingInlineStart: `calc(${depth} * var(--dp-space-4))` }"
    >
      <button
        v-if="scalar === null"
        type="button"
        class="json-node__toggle"
        :aria-expanded="open"
        :aria-label="name ?? ''"
        data-testid="json-node-toggle"
        @click="open = !open"
      >
        <q-icon
          :name="open ? appIcons.expandMore : appIcons.chevronRight"
          size="xs"
        />
      </button>
      <span
        v-else
        class="json-node__spacer"
      />
      <span
        v-if="name !== null"
        class="json-node__name"
      >{{ name }}:</span>
      <template v-if="scalar !== null">
        <span
          v-if="scalar.tone === 'typed'"
          class="json-node__type"
        >{{ scalar.type }}</span>
        <span
          class="json-node__value"
          :class="`json-node__value--${scalar.tone}`"
        >{{ scalar.text }}</span>
      </template>
      <span
        v-else-if="!open"
        class="json-node__summary"
      >{{ closedSummary(value) }}</span>
    </div>
    <template v-if="scalar === null && open">
      <JsonTreeNode
        v-for="child in children"
        :key="child.name"
        :value="child.value"
        :name="child.name"
        :depth="root ? depth : depth + 1"
        :open-levels="openLevels"
      />
    </template>
  </div>
</template>

<style scoped>
.json-node__line {
  display: flex;
  align-items: baseline;
  gap: var(--dp-space-1);
  min-height: 20px;
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-xs);
  white-space: nowrap;
}
.json-node__toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--dp-text-muted);
  cursor: pointer;
}
.json-node__spacer {
  display: inline-block;
  width: 16px;
}
.json-node__name {
  color: var(--dp-text);
}
.json-node__type,
.json-node__summary {
  color: var(--dp-text-muted);
}
.json-node__value {
  overflow: hidden;
  text-overflow: ellipsis;
}
.json-node__value--string {
  color: var(--dp-code-string);
}
.json-node__value--number {
  color: var(--dp-code-number);
}
.json-node__value--word {
  color: var(--dp-code-keyword);
}
.json-node__value--typed {
  color: var(--dp-code-type);
}
</style>
