<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { AdapterTypeInfo, MakeChoice } from "@/client"
import { t } from "@/shared/i18n"
import { AppButton, AppCheckbox, AppForm, AppInput, AppSelect } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * A new source made here, for a type that needs no server (D263).
 *
 * The two ways a service is started, said for a file: left to the server, it
 * asks nothing and the server decides the folder, the name and the sample
 * data; chosen, it asks what is a person's to decide. Where the file lands is
 * the server's answer either way, said once it is made.
 */
const props = defineProps<{
  type: AdapterTypeInfo | null
}>()

const emit = defineEmits<{
  "update:type": [value: AdapterTypeInfo | null]
  make: [payload: { adapterType: string; choice: MakeChoice }]
}>()

const mode = ref<"automatic" | "chosen">("automatic")
const name = ref("")
const folder = ref("")
const sampleData = ref(true)
const wal = ref(false)

// Opened on a type, it starts over: the last database somebody made is not a
// draft of the next one.
watch(
  () => props.type,
  () => {
    mode.value = "automatic"
    name.value = ""
    folder.value = ""
    sampleData.value = true
    wal.value = false
  }
)

const modes = computed(() => [
  { label: t("services.start.automatic"), value: "automatic" },
  { label: t("services.start.chosen"), value: "chosen" },
])

/** What is sent: nothing chosen is the server's to decide, so it is left out. */
const choice = computed<MakeChoice>(() => {
  if (mode.value === "automatic") return {}
  return {
    name: name.value.trim() || null,
    folder: folder.value.trim() || null,
    sample_data: sampleData.value,
    wal: wal.value,
  }
})

function make() {
  const type = props.type
  if (type === null) return
  emit("make", { adapterType: type.name, choice: choice.value })
  emit("update:type", null)
}
</script>

<template>
  <WindowDialog
    :model-value="type !== null"
    size="long-form"
    sizing="stable"
    :title="t('connectors.make_here.title', { title: type?.title ?? '' })"
    :subtitle="t('connectors.make_here.subtitle')"
    data-testid="make-here-dialog"
    @update:model-value="emit('update:type', null)"
  >
    <AppForm layout="section">
      <AppSelect
        v-model="mode"
        :label="t('services.start.how')"
        :options="modes"
        data-testid="make-here-mode"
      />

      <p
        v-if="mode === 'automatic'"
        class="make-here__what"
        data-testid="make-here-automatic-summary"
      >
        {{ t('connectors.make_here.automatic') }}
      </p>

      <template v-else>
        <AppInput
          v-model="name"
          :label="t('connectors.make_here.name')"
          :placeholder="t('connectors.make_here.name_placeholder')"
          autocomplete="off"
          data-testid="make-here-name"
          @keydown.enter="make"
        />
        <AppInput
          v-model="folder"
          :label="t('connectors.make_here.folder')"
          :placeholder="t('connectors.make_here.folder_placeholder')"
          :hint="t('connectors.make_here.folder_hint')"
          autocomplete="off"
          data-testid="make-here-folder"
          @keydown.enter="make"
        />
        <AppCheckbox
          v-model="sampleData"
          :label="t('connectors.make_here.sample_data')"
          data-testid="make-here-sample"
        />
        <AppCheckbox
          v-model="wal"
          :label="t('connectors.make_here.wal')"
          data-testid="make-here-wal"
        />
        <p class="make-here__what">
          {{ t('connectors.make_here.wal_hint') }}
        </p>
      </template>
    </AppForm>

    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        data-testid="make-here-cancel"
        @click="emit('update:type', null)"
      />
      <AppButton
        :label="t('connectors.make_here.make')"
        data-testid="make-here-submit"
        @click="make"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.make-here__what {
  margin: 0;
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
}
</style>
