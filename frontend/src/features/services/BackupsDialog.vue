<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import {
  useBackUp,
  useBackupOffer,
  useBackups,
  useDeleteBackup,
  useRestore,
} from "@/features/services/api"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppEmptyState,
  AppForm,
  AppIconButton,
  AppSpinner,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * The backups of one connection, and the two things one can do with them.
 *
 * A backup is a file in personal storage, so this window lists files rather
 * than rows — the same folder the file source browses, read by name (D87).
 * Both commands start a job, so neither waits: the window can be closed and
 * what is happening is watched beside the connections.
 */
const props = defineProps<{
  connector: { id: string; name: string } | null
}>()

const emit = defineEmits<{ "update:connector": [value: null] }>()

const offer = useBackupOffer(computed(() => props.connector?.id ?? null))
const backups = useBackups()
const backUp = useBackUp()
const restore = useRestore()
const forget = useDeleteBackup()
const toast = useToast()
const confirm = useConfirm()
const working = ref(false)

const files = computed(() => backups.data.value ?? [])
const available = computed(() =>
  offer.data.value?.available === true && !offer.isError.value && !offer.isFetching.value
)

function readableSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function readableTime(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString()
}

async function take() {
  const connector = props.connector
  if (!connector) return
  working.value = true
  try {
    await backUp.mutateAsync(connector.id)
    toast.info(`Copying ${connector.name} out`)
    emit("update:connector", null)
  } catch (cause) {
    toast.error(messageOf(cause, "It could not be copied out"))
  } finally {
    working.value = false
  }
}

/**
 * Putting one back is destructive in a way nothing else here is.
 *
 * Asked in the words of what it does — every object in the dump is dropped
 * from the target first — and the request says so again to the server, which
 * refuses one that does not (D87).
 */
/**
 * Taking one away, which is a file and nothing more.
 *
 * Not a job: removing a file is not minutes of work, so it happens while the
 * window is open and the list is what says it happened. The same file can also
 * be deleted through the file source — this is the second place a person
 * looks, not a second way of storing them.
 */
async function remove(filename: string) {
  const sure = await confirm({
    title: "Delete this backup?",
    message: `${filename} will be removed from your storage. This cannot be undone.`,
    confirmLabel: "Delete",
    danger: true,
  })
  if (!sure) return
  working.value = true
  try {
    await forget.mutateAsync(filename)
    toast.success(`${filename} was deleted`)
  } catch (cause) {
    toast.error(messageOf(cause, "It could not be deleted"))
  } finally {
    working.value = false
  }
}

async function putBack(filename: string) {
  const connector = props.connector
  if (!connector) return
  const sure = await confirm({
    title: "Write this backup back?",
    message:
      `Everything in ${connector.name} that is also in ${filename} will be ` +
      "replaced by what the backup holds. This cannot be undone.",
    confirmLabel: "Restore",
    danger: true,
  })
  if (!sure) return
  working.value = true
  try {
    await restore.mutateAsync({
      connector_id: connector.id,
      filename,
      understood: true,
    })
    toast.info(`Writing ${filename} back into ${connector.name}`)
    emit("update:connector", null)
  } catch (cause) {
    toast.error(messageOf(cause, "It could not be written back"))
  } finally {
    working.value = false
  }
}
</script>

<template>
  <WindowDialog
    :model-value="connector !== null"
    size="medium-form"
    sizing="stable"
    :title="`Backups of ${connector?.name ?? ''}`"
    subtitle="A backup is a file in your own storage."
    data-testid="backups-dialog"
    @update:model-value="emit('update:connector', null)"
  >
    <AppForm layout="section">
      <AppBanner
        v-if="offer.isError.value"
        tone="warning"
      >
        {{ messageOf(offer.error.value, "Backup availability could not be checked") }}
      </AppBanner>
      <AppBanner
        v-if="offer.data.value && !offer.data.value.available"
        tone="warning"
      >
        {{ offer.data.value.reason ?? "This server cannot copy a database out" }}
      </AppBanner>

      <AppSpinner v-if="backups.isLoading.value" />
      <AppEmptyState
        v-else-if="files.length === 0"
        icon="inventory_2"
        text="You have no backups yet."
      />
      <ul
        v-else
        class="backups__list"
      >
        <li
          v-for="file in files"
          :key="file.filename"
          class="backups__row"
          :data-testid="`backup-${file.filename}`"
        >
          <div class="backups__what">
            <span class="backups__name">{{ file.filename }}</span>
            <span class="backups__when">
              {{ readableSize(file.size_bytes) }} · {{ readableTime(file.modified_at) }}
            </span>
          </div>
          <AppButton
            variant="danger-quiet"
            label="Restore"
            :disable="working || !available"
            :data-testid="`restore-${file.filename}`"
            @click="putBack(file.filename)"
          />
          <!-- Deleting a file needs no runtime and no volume to write into, so
               it stays offered where restoring is not. -->
          <AppIconButton
            :icon="appIcons.deleteOutline"
            tooltip="Delete this backup"
            :disable="working"
            :data-testid="`delete-backup-${file.filename}`"
            @click="remove(file.filename)"
          />
        </li>
      </ul>
    </AppForm>

    <template #actions>
      <AppButton
        variant="quiet"
        label="Close"
        @click="emit('update:connector', null)"
      />
      <AppButton
        label="Copy this database out"
        :disable="working || !available"
        :loading="working"
        data-testid="take-backup"
        @click="take"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.backups__list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.backups__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) 0;
}
.backups__row + .backups__row {
  border-top: 1px solid var(--dp-border-faint);
}
.backups__what {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}
.backups__name {
  font-size: var(--dp-font-size);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.backups__when {
  font-size: var(--dp-font-size-xs);
  color: var(--dp-text-muted);
}
</style>
