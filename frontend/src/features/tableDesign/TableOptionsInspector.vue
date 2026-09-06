<script setup lang="ts">
import { computed } from "vue"

import { AppBanner, AppInput, AppSelect, AppTooltip } from "@/shared/ui"

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
  { label: "None", value: "" },
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
        label="Persistence"
        data-testid="table-persistence"
      />
      <AppInput
        model-value=""
        label="Tablespace · optional"
        disable
        data-testid="table-tablespace"
      >
        <AppTooltip>Tablespace selection is not supported by table creation yet.</AppTooltip>
      </AppInput>
    </div>

    <div class="inspector__row">
      <AppInput
        model-value=""
        label="Owner · optional"
        disable
        data-testid="table-owner"
      >
        <AppTooltip>Owner selection is not supported by table creation yet.</AppTooltip>
      </AppInput>
      <AppSelect
        v-model="design.draft.partitionStrategy"
        :options="strategies"
        label="Partition by"
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
      This creates the parent. Rows go into partitions of it, which are made separately, and every
      key of the table must hold its partition columns.
    </AppBanner>
  </div>
</template>

<style scoped>
.inspector {
  display: grid;
  gap: 12px;
}
.inspector__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
}
@container table-designer (max-width: 560px) {
  .inspector__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
