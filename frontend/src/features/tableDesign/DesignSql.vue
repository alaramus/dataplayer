<script setup lang="ts">
import { computed } from "vue"

import { sqlTokens } from "./sqlTokens"

const props = defineProps<{ sql: string }>()
const tokens = computed(() => sqlTokens(props.sql))
</script>

<template>
  <pre
    class="design-sql"
  ><code><span
    v-for="(token, at) in tokens"
    :key="at"
    :class="`design-sql__${token.kind}`"
  >{{ token.text }}</span></code></pre>
</template>

<style scoped>
.design-sql {
  margin: 0;
  padding: 12px;
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.design-sql code {
  font: inherit;
}
.design-sql__keyword {
  color: var(--dp-code-keyword);
}
.design-sql__literal {
  color: var(--dp-code-string);
}
.design-sql__comment {
  color: var(--dp-code-comment);
}
</style>
