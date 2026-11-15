<script setup lang="ts">
import { computed, ref } from "vue"

import { formatSize } from "@/features/catalog/nodes"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppButton,
  AppCheckbox,
  AppEmptyState,
  AppSpinner,
  appIcons,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useMyFiles } from "./api"
import type { StoredFile } from "./letter"

/**
 * Files of the owner's own folder, ticked to go with a letter (D374). Walked
 * a folder at a time; what was ticked in one folder stays ticked in another.
 */
const props = defineProps<{ connectorId: string }>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ add: [files: StoredFile[]] }>()

const path = ref("")
const ticked = ref<Map<string, StoredFile>>(new Map())
const listing = useMyFiles(
  computed(() => props.connectorId),
  path,
  computed(() => open.value)
)

const trail = computed(() => {
  const parts = path.value === "" ? [] : path.value.split("/")
  return parts.map((name, index) => ({ name, path: parts.slice(0, index + 1).join("/") }))
})

function toggle(file: StoredFile, on: boolean) {
  const next = new Map(ticked.value)
  if (on) next.set(file.path, file)
  else next.delete(file.path)
  ticked.value = next
}

function add() {
  emit("add", [...ticked.value.values()])
  ticked.value = new Map()
  open.value = false
}
</script>

<template>
  <WindowDialog
    v-model="open"
    :title="t('mail.my_files.title')"
    size="form"
    sizing="stable"
    data-testid="mail-my-files"
  >
    <div class="my-files">
      <nav class="my-files__trail">
        <AppButton
          variant="quiet"
          size="sm"
          :icon="appIcons.home"
          :label="t('mail.my_files.top')"
          @click="path = ''"
        />
        <template
          v-for="step in trail"
          :key="step.path"
        >
          <span class="my-files__divider">/</span>
          <AppButton
            variant="quiet"
            size="sm"
            :label="step.name"
            @click="path = step.path"
          />
        </template>
      </nav>
      <AppSpinner v-if="listing.isLoading.value" />
      <p
        v-else-if="listing.isError.value"
        class="my-files__problem"
      >
        {{ messageOf(listing.error.value, t("mail.my_files.could_not_read")) }}
      </p>
      <AppEmptyState
        v-else-if="(listing.data.value?.entries.length ?? 0) === 0"
        :text="t('mail.my_files.empty')"
        :icon="appIcons.folder"
        inset
      />
      <ul
        v-else
        class="my-files__list"
      >
        <li
          v-for="entry in listing.data.value?.entries ?? []"
          :key="entry.path"
          class="my-files__entry"
        >
          <AppButton
            v-if="entry.is_directory"
            variant="quiet"
            layout="navigation"
            :icon="appIcons.folder"
            :label="entry.name"
            data-testid="mail-my-folder"
            @click="path = entry.path"
          />
          <template v-else>
            <AppCheckbox
              :model-value="ticked.has(entry.path)"
              :label="entry.name"
              data-testid="mail-my-file"
              @update:model-value="(on: boolean) => toggle({ path: entry.path, name: entry.name, size: entry.size }, on)"
            />
            <span class="my-files__size">{{ formatSize(entry.size) }}</span>
          </template>
        </li>
      </ul>
    </div>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('mail.composer.cancel')"
        @click="open = false"
      />
      <AppButton
        :label="t('mail.my_files.add', { n: ticked.size })"
        :disable="ticked.size === 0"
        data-testid="mail-my-files-add"
        @click="add"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
/* The padding of a form in a window, so a list here sits off its edges as
   every other window's contents do. */
.my-files {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  padding: var(--dp-space-4);
}

.my-files__trail {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--dp-space-half);
}

.my-files__divider {
  color: var(--dp-text-muted);
}

.my-files__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.my-files__entry {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  min-height: var(--dp-row-height);
}

.my-files__size {
  margin-inline-start: auto;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}

.my-files__problem {
  color: var(--dp-content-error);
}
</style>
