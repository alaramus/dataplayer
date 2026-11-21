<script setup lang="ts">
import { computed, ref } from "vue"

import type { PairsBlock } from "@/client"
import { copyText } from "@/shared/clipboard"
import { t } from "@/shared/i18n"
import { AppIconButton, AppInput, appIcons, useToast } from "@/shared/ui"

import { PAIRS_FILTERED_FROM, filterPairs } from "./view"

/**
 * Names and values — a container's environment, its labels (D420). A value
 * the source marked sensitive is dots until its button is pressed, and is
 * copied only once shown (D421): it hides from a glance over a shoulder, not
 * from the reader, who has the JSON beside it.
 */
const props = defineProps<{ block: PairsBlock }>()

const toast = useToast()
const query = ref("")
const shown = ref(new Set<number>())

const filterable = computed(() => props.block.pairs.length > PAIRS_FILTERED_FROM)
const rows = computed(() => {
  const indexed = props.block.pairs.map((pair, index) => ({ pair, index }))
  if (!filterable.value) return indexed
  const kept = new Set(filterPairs(props.block.pairs, query.value))
  return indexed.filter((row) => kept.has(row.pair))
})

function hidden(index: number): boolean {
  return props.block.pairs[index]?.sensitive === true && !shown.value.has(index)
}

function toggle(index: number) {
  const next = new Set(shown.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  shown.value = next
}

async function copy(index: number) {
  const pair = props.block.pairs[index]
  if (pair === undefined || hidden(index)) return
  try {
    await copyText(pair.value)
    toast.success(t("content.view.copied"))
  } catch {
    toast.error(t("content.view.copy_failed"))
  }
}
</script>

<template>
  <div class="view-pairs">
    <AppInput
      v-if="filterable"
      v-model="query"
      class="view-pairs__filter"
      :label="t('content.view.filter')"
      compact
      clearable
      data-testid="view-pairs-filter"
    />
    <dl
      v-if="rows.length > 0"
      class="view-pairs__list"
    >
      <div
        v-for="row in rows"
        :key="row.index"
        class="view-pairs__row"
        data-testid="view-pair"
      >
        <dt class="view-pairs__name">
          {{ row.pair.name }}
        </dt>
        <dd class="view-pairs__value">
          <span
            v-if="hidden(row.index)"
            class="view-pairs__dots"
            :aria-label="t('content.view.hidden')"
            data-testid="view-pair-hidden"
          >••••••••</span>
          <code v-else>{{ row.pair.value }}</code>
          <AppIconButton
            v-if="row.pair.sensitive"
            compact
            :icon="hidden(row.index) ? appIcons.visibility : appIcons.visibilityOff"
            :tooltip="hidden(row.index) ? t('content.view.show') : t('content.view.hide')"
            data-testid="view-pair-reveal"
            @click="toggle(row.index)"
          />
          <AppIconButton
            compact
            :icon="appIcons.copy"
            :tooltip="t('kit.copy.tooltip')"
            :disable="hidden(row.index)"
            @click="copy(row.index)"
          />
        </dd>
      </div>
    </dl>
    <p
      v-else
      class="dp-helper"
    >
      {{ block.pairs.length === 0 ? t("content.view.nothing") : t("content.view.no_match") }}
    </p>
    <p
      v-if="(block.omitted ?? 0) > 0"
      class="dp-meta"
    >
      {{ t("content.view.omitted", { n: block.omitted ?? 0 }) }}
    </p>
  </div>
</template>

<style scoped>
.view-pairs {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}
.view-pairs__filter {
  max-width: var(--dp-width-popover);
}
.view-pairs__list {
  display: grid;
  grid-template-columns: minmax(auto, var(--dp-width-note)) 1fr;
  margin: 0;
}
.view-pairs__row {
  display: contents;
}
.view-pairs__name,
.view-pairs__value {
  padding: var(--dp-space-half) var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
  overflow-wrap: anywhere;
}
.view-pairs__name {
  color: var(--dp-text-muted);
}
.view-pairs__value {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  margin: 0;
}
.view-pairs__value code {
  white-space: pre-wrap;
}
.view-pairs__dots {
  color: var(--dp-text-muted);
  letter-spacing: 0.1em;
}
</style>
