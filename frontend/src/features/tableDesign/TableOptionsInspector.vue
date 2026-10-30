<script setup lang="ts">
import { computed } from "vue"

import { t } from "@/shared/i18n"
import { AppBanner, AppInput, AppSelect, AppTooltip } from "@/shared/ui"

import type { EngineParameter } from "@/client"

import { useDesign } from "./design"

const props = defineProps<{ designId: string }>()

const design = useDesign(props.designId)

const persistence = computed(() =>
  (design.options.value?.persistence_options ?? []).map((choice) => ({
    label: choice.title,
    value: choice.code,
  }))
)
const engines = computed(() =>
  (design.options.value?.engines ?? []).map((option) => ({
    label: option.title,
    value: option.code,
    description: option.description ?? undefined,
  }))
)

/** Another engine takes other columns; one that keeps no key drops the key it had. */
function chooseEngine(code: string): void {
  design.draft.engine = code
  design.draft.engineArguments = {}
  const chosen = design.options.value?.engines?.find((option) => option.code === code)
  if (chosen?.sorted === false) design.draft.primaryKey = []
}

/** The columns a parameter may name: only those of a type it takes. */
function columnsFor(parameter: EngineParameter) {
  const codes = parameter.type_codes ?? []
  const columns = design.draft.columns
    .filter((column) => codes.includes(column.typeCode))
    .map((column) => ({ label: column.name || t("table_design.unnamed"), value: column.id }))
  // A single optional column can be left out again.
  return parameter.many || parameter.required ? columns : [{ label: t("table_design.none"), value: "" }, ...columns]
}

function argument(code: string): string[] {
  return design.draft.engineArguments[code] ?? []
}

function setArgument(code: string, value: unknown): void {
  const ids = Array.isArray(value) ? value.map(String) : value ? [String(value)] : []
  design.draft.engineArguments = { ...design.draft.engineArguments, [code]: ids }
}

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
    <template v-if="engines.length > 1 && design.engine.value">
      <div class="inspector__row">
        <AppSelect
          :model-value="design.engine.value.code"
          :options="engines"
          :label="t('table_design.options.engine')"
          data-testid="table-engine"
          @update:model-value="chooseEngine(String($event))"
        />
        <p class="inspector__note">
          {{ design.engine.value.description }}
        </p>
      </div>
      <div
        v-if="design.engine.value.parameters?.length"
        class="inspector__row"
      >
        <AppSelect
          v-for="parameter in design.engine.value.parameters"
          :key="parameter.code"
          :model-value="parameter.many ? argument(parameter.code) : argument(parameter.code)[0] ?? ''"
          :options="columnsFor(parameter)"
          :label="parameter.title"
          :multiple="parameter.many === true"
          :data-testid="`engine-${parameter.code}`"
          @update:model-value="setArgument(parameter.code, $event)"
        />
      </div>
    </template>
    <div class="inspector__row">
      <AppSelect
        v-if="persistence.length > 1"
        v-model="design.draft.persistence"
        :options="persistence"
        :label="t('table_design.options.persistence')"
        data-testid="table-persistence"
      />
      <AppInput
        v-if="design.abilities.value.tablespaces"
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
        v-if="design.abilities.value.tablespaces"
        model-value=""
        :label="t('table_design.options.owner')"
        disable
        data-testid="table-owner"
      >
        <AppTooltip>{{ t('table_design.options.owner_later') }}</AppTooltip>
      </AppInput>
      <AppSelect
        v-if="strategies.length > 1"
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
.inspector__note {
  margin: 0;
  color: var(--dp-text-muted);
}
.inspector__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--dp-space-3);
  align-items: end;
}
@container table-designer (max-width: 560px) {
  .inspector__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
