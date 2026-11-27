<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { CopyBrief } from "@/client"
import { useCopies, useDeleteCopies, wholeText } from "@/features/copies/api"
import { chosenShown, originLine, sizeLine, useCopiesWindow } from "@/features/copies/copies"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import { t } from "@/shared/i18n"
import { formatDateTime } from "@/shared/i18n/format"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppEmptyState,
  AppIconButton,
  AppInput,
  AppSpinner,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * The copy history (D460): what this person copied in the application, to
 * copy again or to delete one, several or all of. Opened from the right rail
 * and drawn once by the workspace.
 */
const window = useCopiesWindow()
const toast = useToast()
const confirm = useConfirm()

const search = ref("")
// The query follows the field a moment behind, so typing a word is one request.
const asked = ref("")
let pause: ReturnType<typeof setTimeout> | undefined
watch(search, (value) => {
  clearTimeout(pause)
  pause = setTimeout(() => (asked.value = value ?? ""), 250)
})

const copies = useCopies(asked, window.open)
const deleting = useDeleteCopies()

const shown = computed<CopyBrief[]>(() => copies.data.value?.items ?? [])
const total = computed(() => copies.data.value?.total ?? 0)
const chosen = ref(new Set<string>())
const chosenIds = computed(() => chosenShown(chosen.value, shown.value))
const allChosen = computed(() => shown.value.length > 0 && chosenIds.value.length === shown.value.length)

watch(window.open, (open) => {
  if (!open) chosen.value = new Set()
})

function choose(id: string, on: boolean) {
  const next = new Set(chosen.value)
  if (on) next.add(id)
  else next.delete(id)
  chosen.value = next
}

function chooseAll(on: boolean) {
  chosen.value = on ? new Set(shown.value.map((copy) => copy.id)) : new Set()
}

async function copyAgain(copy: CopyBrief) {
  try {
    const text = copy.preview.length < copy.length ? await wholeText(copy.id) : copy.preview
    // Not kept again: the row would jump to the top under the pointer while
    // the person is still working in the list (D460).
    await copyText(text, { history: true })
    toast.success(t("copies.window.copied"))
  } catch (cause) {
    toast.error(messageOf(cause, t("copies.window.copy_failed")))
  }
}

async function remove(ids: string[] | null) {
  try {
    await deleting.mutateAsync(ids)
    const next = new Set(chosen.value)
    for (const id of ids ?? [...next]) next.delete(id)
    chosen.value = next
  } catch (cause) {
    toast.error(messageOf(cause, t("copies.window.delete_failed")))
  }
}

async function removeChosen() {
  const ids = chosenIds.value
  if (ids.length === 0) return
  const sure = await confirm({
    title: t("copies.window.delete_chosen_title"),
    message: t("copies.window.delete_chosen_message", { n: ids.length }, ids.length),
    confirmLabel: t("copies.window.delete"),
    danger: true,
  })
  if (sure) await remove(ids)
}

async function clearAll() {
  const sure = await confirm({
    title: t("copies.window.clear_title"),
    message: t("copies.window.clear_message", { n: total.value }, total.value),
    confirmLabel: t("copies.window.clear"),
    danger: true,
  })
  if (sure) await remove(null)
}
</script>

<template>
  <WindowDialog
    :model-value="window.open.value"
    size="form"
    sizing="stable"
    :title="t('copies.window.title')"
    :subtitle="t('copies.window.subtitle')"
    data-testid="copies-window"
    @update:model-value="window.close()"
  >
    <div class="copies">
      <AppInput
        v-model="search"
        :placeholder="t('copies.window.search')"
        :prepend-icon="appIcons.search"
        compact
        clearable
        data-testid="copies-search"
      />
      <div
        v-if="total > 0"
        class="copies__bar"
      >
        <AppCheckbox
          :model-value="allChosen"
          :indeterminate="chosenIds.length > 0 && !allChosen"
          :disable="shown.length === 0"
          :label="chosenIds.length > 0
            ? t('copies.window.chosen', { n: chosenIds.length }, chosenIds.length)
            : t('copies.window.count', { n: total }, total)"
          dense
          data-testid="copies-choose-all"
          @update:model-value="chooseAll"
        />
        <span class="copies__commands">
          <AppButton
            v-if="chosenIds.length > 0"
            variant="danger-quiet"
            size="sm"
            :icon="appIcons.delete"
            :label="t('copies.window.delete_chosen')"
            :disable="deleting.isPending.value"
            data-testid="copies-delete-chosen"
            @click="removeChosen"
          />
          <AppButton
            variant="danger-quiet"
            size="sm"
            :icon="appIcons.deleteSweep"
            :label="t('copies.window.clear')"
            :disable="deleting.isPending.value"
            data-testid="copies-clear"
            @click="clearAll"
          />
        </span>
      </div>

      <AppSpinner v-if="copies.isLoading.value" />
      <AppBanner
        v-else-if="copies.isError.value"
        tone="warning"
      >
        {{ messageOf(copies.error.value, t('copies.window.read_failed')) }}
      </AppBanner>
      <AppEmptyState
        v-else-if="total === 0"
        :icon="appIcons.contentPaste"
        :text="t('copies.window.empty')"
        data-testid="copies-empty"
      />
      <AppEmptyState
        v-else-if="shown.length === 0"
        :text="t('copies.window.none_found')"
        data-testid="copies-none-found"
      />
      <ul
        v-else
        class="copies__list"
      >
        <li
          v-for="copy in shown"
          :key="copy.id"
          class="copies__item"
          data-testid="copies-item"
        >
          <AppCheckbox
            :model-value="chosen.has(copy.id)"
            dense
            :aria-label="t('copies.window.choose')"
            data-testid="copies-choose"
            @update:model-value="choose(copy.id, $event)"
          />
          <div class="copies__what">
            <pre
              class="copies__text"
              data-testid="copies-text"
            >{{ copy.preview }}</pre>
            <span class="dp-helper">
              {{ originLine(copy) }} · <time :datetime="copy.copied_at">{{ formatDateTime(copy.copied_at) }}</time>
              <template v-if="sizeLine(copy)"> · {{ sizeLine(copy) }}</template>
            </span>
          </div>
          <span class="copies__actions">
            <AppIconButton
              :icon="appIcons.copy"
              :tooltip="t('copies.window.copy_again')"
              data-testid="copies-copy"
              @click="copyAgain(copy)"
            />
            <AppIconButton
              :icon="appIcons.delete"
              :tooltip="t('copies.window.delete_one')"
              variant="danger-quiet"
              :disable="deleting.isPending.value"
              data-testid="copies-delete"
              @click="remove([copy.id])"
            />
          </span>
        </li>
      </ul>
    </div>

    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.close')"
        @click="window.close()"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
/* A window's content owns its inset; the padding of a form's section, which
   the subtitle above lines up with. */
.copies {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  min-height: 0;
  padding: var(--dp-space-4);
}
.copies__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-3);
}
.copies__commands {
  display: flex;
  gap: var(--dp-space-1);
}
.copies__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.copies__item {
  display: flex;
  align-items: flex-start;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) 0;
  border-top: 1px solid var(--dp-border-faint);
}
.copies__what {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
}
/* Three lines of the start of a copy: enough to tell one from another. */
.copies__text {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-mono);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
}
.copies__actions {
  display: flex;
}
</style>
