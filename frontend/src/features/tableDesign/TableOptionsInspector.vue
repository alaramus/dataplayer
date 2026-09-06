<script setup lang="ts">
import { computed } from "vue"

import { AppBanner, AppInput, AppSelect } from "@/shared/ui"

import { useDesign } from "./design"

const props = defineProps<{ designId: string }>()

const design = useDesign(props.designId)

const persistence = computed(() =>
  (design.options.value?.persistence_options ?? []).map((choice) => ({
    label: choice.title,
    value: choice.code,
  }))
)
const strategies = computed(() => [
  { label: "Not split into partitions", value: "" },
  ...(design.options.value?.partition_strategies ?? []).map((choice) => ({
    label: choice.title,
    value: choice.code,
  })),
])
</script>

<template>
  <div
    class="inspector"
    data-testid="table-options"
  >
    <div class="inspector__row">
      <AppSelect
        v-model="design.draft.persistence"
        :options="persistence"
        label="Kept"
        hint="An unlogged table is faster and does not survive a crash"
        data-testid="table-persistence"
      />
      <AppInput
        v-model="design.draft.comment"
        label="Comment"
      />
    </div>

    <div class="inspector__row">
      <AppSelect
        v-model="design.draft.partitionStrategy"
        :options="strategies"
        label="Split by"
        data-testid="table-partition"
      />
      <AppSelect
        v-if="design.draft.partitionStrategy !== ''"
        v-model="design.draft.partitionColumnIds"
        :options="design.columnChoices.value"
        label="Partition columns"
        multiple
      />
    </div>
    <AppBanner
      v-if="design.draft.partitionStrategy !== ''"
      tone="info"
    >
      This creates the parent. Rows go into partitions of it, which are made
      separately, and every key of the table must hold its partition columns.
    </AppBanner>
  </div>
</template>

<style scoped>
.inspector {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}

.inspector__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
  align-items: flex-start;
}

.inspector__row > * {
  flex: 1 1 200px;
  min-width: 0;
}
</style>
