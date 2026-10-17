<script setup lang="ts">
import { computed, ref, useId } from "vue"

import { t } from "@/shared/i18n"
import { AppButton, AppInput } from "@/shared/ui"

import { useDesign } from "./design"
import PredicateEditor from "./PredicateEditor.vue"
import { predicateLabel } from "./predicateLabel"

const props = defineProps<{
  designId: string
  owner: "index" | "check"
  ownerId: string
  testid: string
  label: string
}>()
const { draft } = useDesign(props.designId)
const expanded = ref(false)
const editorId = useId()
const label = computed(() => {
  const predicate =
    props.owner === "index"
      ? draft.indexes.find((index) => index.id === props.ownerId)?.predicate
      : draft.checks.find((check) => check.id === props.ownerId)?.predicate
  return predicate ? predicateLabel(predicate, draft.columns) : ""
})
</script>

<template>
  <div class="predicate-field">
    <AppInput
      :model-value="label"
      :label="props.label"
      readonly
      :aria-label="t('table_design.predicate.edit', { label: props.label })"
      :aria-expanded="expanded"
      :aria-controls="editorId"
      :data-testid="`${testid}-field`"
      @click="expanded = !expanded"
      @keydown.enter.prevent="expanded = !expanded"
      @keydown.space.prevent="expanded = !expanded"
    />
    <div
      v-if="expanded"
      :id="editorId"
      class="predicate-field__editor"
    >
      <PredicateEditor
        :design-id="designId"
        :owner="owner"
        :owner-id="ownerId"
        :testid="testid"
      />
      <AppButton
        variant="quiet"
        :label="t('table_design.predicate.done')"
        @click="expanded = false"
      />
    </div>
  </div>
</template>

<style scoped>
.predicate-field {
  min-width: 0;
}
.predicate-field__editor {
  display: grid;
  gap: var(--dp-space-2);
  margin-top: var(--dp-space-2);
  padding: var(--dp-space-2);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
}
.predicate-field__editor > :last-child {
  justify-self: end;
}
</style>
