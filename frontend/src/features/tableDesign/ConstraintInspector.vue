<script setup lang="ts">
import { computed } from "vue"

import { AppCheckbox, AppInput, AppSelect } from "@/shared/ui"

import { useDesign } from "./design"
import type { DraftCheck, DraftUnique } from "./draft"
import PredicateEditor from "./PredicateEditor.vue"

const props = defineProps<{ designId: string; constraintId: string }>()

const design = useDesign(props.designId)

const unique = computed<DraftUnique | undefined>(() =>
  design.draft.uniques.find((item) => item.id === props.constraintId)
)
const check = computed<DraftCheck | undefined>(() =>
  design.draft.checks.find((item) => item.id === props.constraintId)
)

const nullsMayRepeat = computed(
  () => design.options.value?.nulls_not_distinct_supported === true
)
</script>

<template>
  <div
    v-if="unique"
    class="inspector"
    data-testid="unique-inspector"
  >
    <div class="inspector__row">
      <AppInput
        v-model="unique.name"
        label="Name"
        hint="Left empty, the database names it"
      />
      <AppSelect
        v-model="unique.columnIds"
        :options="design.columnChoices.value"
        label="Columns"
        multiple
        data-testid="unique-columns"
      />
    </div>
    <div class="inspector__row">
      <AppCheckbox
        v-model="unique.nullsNotDistinct"
        label="Two empty values count as the same"
        dense
        :disable="!nullsMayRepeat"
      />
      <AppCheckbox
        v-model="unique.deferrable"
        label="May be checked at the end of a transaction"
        dense
      />
      <AppCheckbox
        v-model="unique.initiallyDeferred"
        label="Checked at the end by default"
        dense
        :disable="!unique.deferrable"
      />
    </div>
  </div>

  <div
    v-else-if="check"
    class="inspector"
    data-testid="check-inspector"
  >
    <AppInput
      v-model="check.name"
      label="Name"
      hint="Left empty, the database names it"
    />
    <PredicateEditor
      :design-id="designId"
      owner="check"
      :owner-id="check.id"
      testid="check-predicate"
    />
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
  align-items: center;
}

.inspector__row > * {
  flex: 1 1 180px;
  min-width: 0;
}
</style>
