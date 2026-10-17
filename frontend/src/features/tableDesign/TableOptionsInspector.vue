<script setup lang="ts">
import { computed } from "vue"

import { t } from "@/shared/i18n"
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
  { label: t("table_design.none"), value: "" },
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
        :label="t('table_design.options.persistence')"
        data-testid="table-persistence"
      />
      <AppInput
        model-value=""
        :label="t('table_design.options.tablespace')"
        disable
        data-testid="table-tablespace"
      >
        <AppTooltip>{{ t('table_design.options.tablespace_later') }}</AppTooltip>
      </AppInput>
    </div>

    <div class="inspector__row">
      <AppInput
        model-value=""
        :label="t('table_design.options.owner')"
        disable
        data-testid="table-owner"
      >
        <AppTooltip>{{ t('table_design.options.owner_later') }}</AppTooltip>
      </AppInput>
      <AppSelect
        v-model="design.draft.partitionStrategy"
        :options="strategies"
        :label="t('table_design.options.partition_by')"
        data-testid="table-partition"
      />
      <AppSelect
        v-if="design.draft.partitionStrategy !== ''"
        v-model="design.draft.partitionColumnIds"
        :options="design.columnChoices.value"
        :label="t('table_design.options.partition_columns')"
        multiple
      />
    </div>
    <AppBanner
      v-if="design.draft.partitionStrategy !== ''"
      tone="info"
    >
      {{ t('table_design.options.partitioned') }}
    </AppBanner>
  </div>
</template>

<style scoped>
.inspector {
  display: grid;
  gap: var(--dp-space-3);
}
.inspector__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--dp-space-3);
  align-items: start;
}
@container table-designer (max-width: 560px) {
  .inspector__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
