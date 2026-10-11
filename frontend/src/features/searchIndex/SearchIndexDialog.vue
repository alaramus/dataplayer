<script setup lang="ts">
import { computed, ref, watch } from "vue"

import {
  useAddContents,
  useChangeKeep,
  useKeepState,
  useRefreshKeep,
  useRemoveContents,
} from "@/features/searchIndex/api"
import { useSearchIndexWindow } from "@/features/searchIndex/searchIndexWindow"
import {
  DEFAULT_WINDOW,
  KEEP_WINDOWS,
  type KeepWindow,
  contentsLine,
  folderName,
  statusLine,
} from "@/features/searchIndex/state"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppForm,
  AppSelect,
  AppSpinner,
  AppToggle,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * Whether one connection keeps a list of its names for search, and how fresh
 * (D212). Opened from the catalog's Actions menu and from wherever a kept list
 * is mentioned; drawn once by the workspace.
 *
 * Only the owner changes it. Anybody the connection is shared with sees the
 * same window with its controls switched off, which is how they learn what is
 * kept of a connection they did not make.
 */
const window = useSearchIndexWindow()
const connectorId = computed(() => window.asked.value?.id ?? null)
const state = useKeepState(connectorId)
const change = useChangeKeep()
const refresh = useRefreshKeep()
const addContents = useAddContents()
const removeContents = useRemoveContents()
const toast = useToast()

const keep = ref(false)
const windowSeconds = ref<KeepWindow>(DEFAULT_WINDOW)
const saving = ref(false)

const current = computed(() => state.data.value ?? null)
const mayChange = computed(() => current.value?.may_change === true)
const available = computed(() => current.value?.available !== false)
const kept = computed(() => current.value !== null && current.value.status !== "off")
const changed = computed(
  () =>
    current.value !== null &&
    (keep.value !== kept.value ||
      (keep.value && windowSeconds.value !== (current.value.window_seconds ?? DEFAULT_WINDOW)))
)

// What the server says replaces the draft whenever another connection is
// opened, and once the first answer arrives — never while somebody edits.
watch(
  () => [connectorId.value, current.value?.connector_id] as const,
  () => {
    keep.value = kept.value
    windowSeconds.value = current.value?.window_seconds ?? DEFAULT_WINDOW
  },
  { immediate: true }
)

const windowOptions = KEEP_WINDOWS.map((one) => ({ label: one.label, value: one.value }))

function chooseWindow(value: unknown) {
  const found = KEEP_WINDOWS.find((one) => one.value === Number(value))
  if (found) windowSeconds.value = found.value
}

async function save() {
  const id = connectorId.value
  if (id === null) return
  saving.value = true
  try {
    await change.mutateAsync({
      connectorId: id,
      body: { keep: keep.value, window_seconds: windowSeconds.value },
    })
    toast.success(
      keep.value
        ? `The names of ${window.asked.value?.name ?? "this connection"} will be kept`
        : `The kept names of ${window.asked.value?.name ?? "this connection"} were deleted`
    )
  } catch (cause) {
    toast.error(messageOf(cause, "The search index could not be changed"))
  } finally {
    saving.value = false
  }
}

/** Where the window offers to keep what files hold: the folder it was opened in. */
const offeredFolder = computed(() => {
  const folder = window.asked.value?.folder ?? null
  const scopes = current.value?.contents ?? []
  const id = folder?.id ?? ""
  if (scopes.some((scope) => scope.node_id === id)) return null
  return { id, label: folder === null ? "the whole connection" : folder.label }
})

async function keepContents() {
  const id = connectorId.value
  const folder = offeredFolder.value
  if (id === null || folder === null) return
  try {
    await addContents.mutateAsync({ connectorId: id, nodeId: folder.id || null })
  } catch (cause) {
    toast.error(messageOf(cause, "What the files hold could not be kept"))
  }
}

async function stopContents(nodeId: string) {
  const id = connectorId.value
  if (id === null) return
  try {
    await removeContents.mutateAsync({ connectorId: id, nodeId })
  } catch (cause) {
    toast.error(messageOf(cause, "It could not be stopped"))
  }
}

async function readAgain() {
  const id = connectorId.value
  if (id === null) return
  try {
    await refresh.mutateAsync(id)
  } catch (cause) {
    toast.error(messageOf(cause, "The names could not be asked for again"))
  }
}
</script>

<template>
  <WindowDialog
    :model-value="window.asked.value !== null"
    size="medium-form"
    sizing="stable"
    :title="`Search index of ${window.asked.value?.name ?? ''}`"
    subtitle="Find what this connection holds by name without asking its server."
    data-testid="search-index-dialog"
    @update:model-value="window.close()"
  >
    <AppSpinner v-if="state.isLoading.value" />
    <AppBanner
      v-else-if="state.isError.value"
      tone="warning"
    >
      {{ messageOf(state.error.value, "The search index could not be read") }}
    </AppBanner>
    <AppForm
      v-else-if="current"
      layout="section"
    >
      <AppBanner
        v-if="!available"
        tone="info"
      >
        This kind of source cannot keep its names.
      </AppBanner>
      <AppBanner
        v-else-if="!mayChange"
        tone="info"
      >
        Only {{ current.owner_email ?? "its owner" }} decides whether its names are kept.
      </AppBanner>

      <AppToggle
        v-model="keep"
        label="Keep a list of names for search"
        :disable="!mayChange || !available"
        data-testid="search-index-keep"
      />
      <span class="dp-helper">
        The names of tables, keys, folders and files are read with the owner's
        credentials and copied into this server's database as plain text.
        Switching this off deletes the copy, and any text kept with it.
      </span>
      <AppSelect
        :model-value="windowSeconds"
        :options="windowOptions"
        label="Read again within"
        hint="Older than this, the search asks the server instead."
        :disable="!mayChange || !keep"
        data-testid="search-index-window"
        @update:model-value="chooseWindow"
      />

      <section
        v-if="kept"
        class="search-index__state"
      >
        <span
          class="search-index__line"
          data-testid="search-index-state"
        >{{ statusLine(current) }}</span>
        <AppButton
          v-if="mayChange"
          variant="secondary"
          size="sm"
          label="Read now"
          :disable="current.status === 'reading' || current.refresh_asked === true"
          data-testid="search-index-refresh"
          @click="readAgain"
        />
      </section>

      <section
        v-if="current.contents_available"
        class="search-index__contents"
        data-testid="search-index-contents"
      >
        <h3 class="dp-section-title">
          What files hold
        </h3>
        <span class="dp-helper">
          The text of the files below a folder, copied the same way, so a word
          inside them is found on Enter without reading them again. Binary files
          and files above the server's size limit are left out.
        </span>
        <ul class="search-index__scopes">
          <li
            v-for="scope in current.contents ?? []"
            :key="scope.node_id"
            class="search-index__scope"
            :data-testid="`search-index-scope-${scope.node_id || 'root'}`"
          >
            <div class="search-index__scope-what">
              <span class="search-index__scope-name">{{ folderName(scope.node_id) }}</span>
              <span class="dp-helper">{{ contentsLine(scope) }}</span>
            </div>
            <AppButton
              v-if="mayChange"
              variant="quiet"
              size="sm"
              label="Stop"
              @click="stopContents(scope.node_id)"
            />
          </li>
        </ul>
        <AppButton
          v-if="mayChange && offeredFolder"
          variant="secondary"
          size="sm"
          :label="`Keep what files hold in ${offeredFolder.label}`"
          :disable="!kept"
          data-testid="search-index-keep-contents"
          @click="keepContents"
        />
        <span
          v-if="mayChange && offeredFolder && !kept"
          class="dp-helper"
        >Keep the names first: the files are found through them.</span>
      </section>
    </AppForm>

    <template #actions>
      <AppButton
        variant="quiet"
        label="Close"
        @click="window.close()"
      />
      <AppButton
        v-if="mayChange"
        label="Save"
        :disable="!changed || saving"
        data-testid="search-index-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.search-index__state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-3);
}
.search-index__line {
  min-width: 0;
  overflow-wrap: anywhere;
}
.search-index__contents {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--dp-space-2);
}
.search-index__scopes {
  list-style: none;
  margin: 0;
  padding: 0;
  width: 100%;
}
.search-index__scope {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-3);
  padding: var(--dp-space-1) 0;
}
.search-index__scope-what {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.search-index__scope-name {
  overflow-wrap: anywhere;
}
</style>
