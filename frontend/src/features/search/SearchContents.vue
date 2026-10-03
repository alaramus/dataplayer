<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query"
import { computed, ref, watch } from "vue"

import { SearchService } from "@/client"
import { startedInThisTab } from "@/features/activity/transfers"
import { rememberAnswer, shouldAsk } from "@/features/catalog/contentSearch"
import { useCancelJob } from "@/features/services/api"
import { messageOf } from "@/shared/api/errors"
import { AppButton, AppCheckbox, AppOption, useConfirm, useToast } from "@/shared/ui"

import { placeSentence, rememberContentsWords } from "./contents"
import type { ContentsChoice } from "./contents"
import { useHitActions } from "./openers"
import { hitOption } from "./rows"

/**
 * "Search inside files" in the Search tab (S7): the connections of the answer
 * that can be read inside, chosen; D76's warning, asked once; then a job whose
 * progress is in the footer (D95) and whose matches are read here while the
 * server holds them.
 */
const props = defineProps<{
  panelId: string
  choices: ContentsChoice[]
  words: string
}>()

/** The search whose matches are shown; set from Recent's "Show results" too. */
const jobId = defineModel<string | null>("jobId", { default: null })

const confirm = useConfirm()
const toast = useToast()
const cancel = useCancelJob()
const hitActions = useHitActions(() => props.panelId)

const choosing = ref(false)
const picked = ref<ReadonlySet<string>>(new Set())
const starting = ref(false)

// Nothing is ticked for the person: reading every file of every connection
// they have is the expensive mistake one press must not make. A tick stays
// while its connection is still offered.
watch(
  () => props.choices.map((one) => one.connectorId).join(","),
  () => {
    const offered = new Set(props.choices.map((one) => one.connectorId))
    picked.value = new Set([...picked.value].filter((one) => offered.has(one)))
  }
)

function pick(connectorId: string, on: boolean) {
  const next = new Set(picked.value)
  if (on) next.add(connectorId)
  else next.delete(connectorId)
  picked.value = next
}

/** D76's warning, once; the answer is this browser's (`contentSearch.ts`). */
async function agreedToRead(): Promise<boolean> {
  if (!shouldAsk(localStorage)) return true
  return await confirm({
    title: "Search inside files",
    message:
      "Every file in the chosen connections will be opened and read, which can " +
      "take minutes. Binary files and files over 8 MB (1 MB over SSH) are skipped.",
    confirmLabel: "Search inside",
    rememberLabel: "Do not ask again",
    onRemember: () => {
      rememberAnswer(localStorage, false)
    },
  })
}

async function begin() {
  const chosen = props.choices.filter((one) => picked.value.has(one.connectorId))
  if (chosen.length === 0 || starting.value) return
  if (!(await agreedToRead())) return
  starting.value = true
  try {
    const { data: job } = await SearchService.searchContents({
      body: { words: props.words, connector_ids: chosen.map((one) => one.connectorId) },
    })
    rememberContentsWords(job.id, props.words)
    startedInThisTab(job.id)
    jobId.value = job.id
    choosing.value = false
  } catch (cause) {
    toast.error(messageOf(cause, "The search inside files could not be started"))
  } finally {
    starting.value = false
  }
}

const found = useQuery({
  queryKey: computed(() => ["search-contents", jobId.value] as const),
  enabled: computed(() => jobId.value !== null),
  queryFn: async ({ signal }) =>
    (await SearchService.readSearchContents({ path: { job_id: jobId.value ?? "" }, signal })).data,
  refetchInterval: (query) => (query.state.data?.finished === true ? false : 1000),
})

const answer = computed(() => (jobId.value === null ? null : (found.data.value ?? null)))
const running = computed(() => answer.value !== null && !answer.value.finished)
const expired = computed(() => answer.value !== null && !answer.value.held)

const summary = computed(() => {
  const shown = answer.value
  if (shown === null) return found.isError.value ? "The matches could not be read" : ""
  if (!shown.held) return "These matches are no longer held"
  const count = shown.hits.length
  const what = count === 0 ? "Nothing found" : count === 1 ? "1 match" : `${String(count)} matches`
  return running.value ? `Searching inside files… ${what} so far` : `${what} inside files`
})

const places = computed(() =>
  (answer.value?.places ?? []).flatMap((place) => {
    const said = placeSentence(place)
    return said === null ? [] : [{ key: place.connector_id, text: `${place.name}: ${said}` }]
  })
)

async function stop() {
  if (jobId.value === null) return
  try {
    await cancel.mutateAsync(jobId.value)
  } catch (cause) {
    toast.error(messageOf(cause, "The search could not be stopped"))
  }
}

function again() {
  jobId.value = null
  choosing.value = true
}

const offered = computed(() => props.choices.length > 0 && props.words !== "")
</script>

<template>
  <section
    v-if="offered || jobId !== null"
    class="search-contents"
    aria-label="Inside files"
    data-testid="search-contents"
  >
    <h3 class="search-contents__title">
      <span>Inside files</span>
      <AppButton
        v-if="offered && jobId === null && !choosing"
        variant="quiet"
        size="sm"
        label="Search inside files"
        data-testid="search-contents-offer"
        @click="choosing = true"
      />
      <AppButton
        v-if="running"
        variant="quiet"
        size="sm"
        label="Stop"
        :loading="cancel.isPending.value"
        data-testid="search-contents-stop"
        @click="stop"
      />
      <AppButton
        v-if="offered && jobId !== null && !running"
        variant="quiet"
        size="sm"
        label="Search again"
        data-testid="search-contents-again"
        @click="again"
      />
    </h3>

    <div
      v-if="choosing"
      class="search-contents__choose"
      data-testid="search-contents-choose"
    >
      <AppCheckbox
        v-for="one in choices"
        :key="one.connectorId"
        dense
        :label="one.name"
        data-testid="search-contents-choice"
        :model-value="picked.has(one.connectorId)"
        @update:model-value="pick(one.connectorId, $event)"
      />
      <span class="search-contents__actions">
        <AppButton
          variant="primary"
          size="sm"
          label="Search inside"
          :disabled="picked.size === 0"
          :loading="starting"
          data-testid="search-contents-start"
          @click="begin"
        />
        <AppButton
          variant="quiet"
          size="sm"
          label="Cancel"
          @click="choosing = false"
        />
      </span>
    </div>

    <p
      v-if="summary"
      class="search-contents__line"
      role="status"
      data-testid="search-contents-summary"
    >
      {{ summary }}
    </p>
    <template v-if="!expired">
      <p
        v-for="place in places"
        :key="place.key"
        class="search-contents__line"
      >
        {{ place.text }}
      </p>
      <AppOption
        v-for="hit in answer?.hits ?? []"
        :key="hit.key"
        :option="hitOption(hit)"
        clickable
        dense
        data-testid="search-contents-hit"
        @click="hitActions.open(hit)"
        @action="hitActions.showInCatalog(hit)"
      />
    </template>
  </section>
</template>

<style scoped>
.search-contents {
  border-bottom: 1px solid var(--dp-border-faint);
}
.search-contents__title {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  margin: 0;
  padding: var(--dp-space-2) var(--dp-space-3) var(--dp-space-1);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
  font-weight: 500;
  line-height: var(--dp-line-height-sm);
  text-transform: uppercase;
}
.search-contents__title :deep(.q-btn) {
  text-transform: none;
}
.search-contents__choose {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--dp-space-2);
  padding: 0 var(--dp-space-3) var(--dp-space-2);
}
.search-contents__actions {
  display: inline-flex;
  gap: var(--dp-space-1);
}
.search-contents__line {
  margin: 0;
  padding: 0 var(--dp-space-3);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
}
</style>
