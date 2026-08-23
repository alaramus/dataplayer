<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { AdapterTypeInfo } from "@/client"
import AdapterDetailPanel from "@/features/connectors/AdapterDetailPanel.vue"
import AdapterTile from "@/features/connectors/AdapterTile.vue"
import { ALL_CATEGORIES, categoryCounts, searchAdapters } from "@/features/connectors/adapterSearch"
import { categoryIcon } from "@/features/connectors/adapters"
import { useAdapterTypes } from "@/features/connectors/api"
import { AppButton, AppDialog, AppEmptyState, AppInput, AppSpinner } from "@/shared/ui"

/**
 * The first of the two steps of adding a connection: which kind of source.
 *
 * A window of its own rather than a step inside the form. The two are
 * different sizes — a grid needs 900px, a form 520 — and one component that
 * changed width between steps would carry two roles as well. Editing an
 * existing connection then opens the form directly, with nothing to say about
 * a catalog it never came from. See the spec, K3.
 */
const props = defineProps<{ modelValue: boolean }>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  pick: [adapterType: string]
}>()

const adapterTypes = useAdapterTypes()

const query = ref("")
const category = ref<string>(ALL_CATEGORIES)
const selectedName = ref<string | null>(null)

const types = computed(() => adapterTypes.data.value ?? [])
const categories = computed(() => categoryCounts(types.value))

const searching = computed(() => query.value.trim() !== "")

/**
 * Searching is not filtering: a query is asked of every type there is.
 *
 * A search narrowed to the selected category would answer "nothing found" for
 * a type that is plainly there, which is the one answer a search must never
 * give wrongly.
 */
const visible = computed<AdapterTypeInfo[]>(() => {
  if (searching.value) return searchAdapters(types.value, query.value)
  if (category.value === ALL_CATEGORIES) return types.value
  return types.value.filter((type) => type.category === category.value)
})

const selected = computed(
  () => visible.value.find((type) => type.name === selectedName.value) ?? null
)

// Reopened, the catalog starts where it started last time: a query left over
// from the previous visit would hide most of what there is to choose from.
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    query.value = ""
    category.value = ALL_CATEGORIES
    selectedName.value = null
  }
)

function selectCategory(id: string) {
  query.value = ""
  category.value = id
}

function pick(type: AdapterTypeInfo) {
  emit("pick", type.name)
}
</script>

<template>
  <AppDialog
    :model-value="modelValue"
    size="lg"
    title="New connection"
    subtitle="Pick the kind of source to connect to."
    data-testid="adapter-catalog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="adapter-catalog">
      <!-- Plain rows and not AppMenu: a menu is a list of commands that
           closes when one is chosen, and this is a filter that stays. -->
      <div class="adapter-catalog__sidebar">
        <div
          v-for="row in categories"
          :key="row.id"
          role="button"
          tabindex="0"
          class="adapter-catalog__category"
          :class="{
            'adapter-catalog__category--active': !searching && row.id === category,
          }"
          :data-testid="`adapter-category-${row.id}`"
          @click="selectCategory(row.id)"
          @keydown.enter="selectCategory(row.id)"
          @keydown.space.prevent="selectCategory(row.id)"
        >
          <q-icon
            :name="row.id === ALL_CATEGORIES ? 'apps' : categoryIcon(row.id)"
            size="18px"
          />
          <span class="adapter-catalog__category-name">{{ row.title }}</span>
          <span class="adapter-catalog__count">{{ row.count }}</span>
        </div>
      </div>

      <div class="adapter-catalog__main">
        <AppInput
          v-model="query"
          clearable
          placeholder="Search by name or by what it can do"
          data-testid="adapter-search"
        >
          <template #prepend>
            <q-icon name="search" />
          </template>
        </AppInput>

        <AppSpinner v-if="adapterTypes.isLoading.value" />

        <div
          v-else
          class="adapter-catalog__grid"
        >
          <AdapterTile
            v-for="type in visible"
            :key="type.name"
            :type="type"
            :selected="type.name === selectedName"
            @pick="selectedName = type.name"
            @open="pick(type)"
          />

          <div
            v-if="visible.length === 0"
            class="adapter-catalog__empty"
          >
            <AppEmptyState
              icon="search_off"
              text="No source type matches that."
            />
          </div>
        </div>
      </div>

      <AdapterDetailPanel
        :type="selected"
        @create="selected && pick(selected)"
      />
    </div>

    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('update:modelValue', false)"
      />
    </template>
  </AppDialog>
</template>

<style scoped>
/* A box of a settled height: the three columns scroll inside it rather than
   the window growing with the number of source types. */
.adapter-catalog {
  display: flex;
  min-height: 0;
  height: min(60vh, 460px);
  border-top: 1px solid var(--dp-border);
  border-bottom: 1px solid var(--dp-border);
}
.adapter-catalog__sidebar {
  flex: none;
  width: clamp(150px, 22%, 220px);
  min-height: 0;
  overflow-y: auto;
  border-right: 1px solid var(--dp-border);
}
.adapter-catalog__category {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  cursor: pointer;
  min-width: 0;
}
.adapter-catalog__category:hover {
  background: var(--dp-hover);
}
.adapter-catalog__category--active {
  background: var(--dp-selected);
  font-weight: 500;
}
.adapter-catalog__category-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.adapter-catalog__count {
  font-size: 12px;
  opacity: 0.6;
}
.adapter-catalog__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
}
.adapter-catalog__grid {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  /* min(180px, 100%) so a viewport narrower than one tile still gets a single
     column that fits, rather than a track overflowing its container. */
  grid-template-columns: repeat(auto-fill, minmax(min(180px, 100%), 1fr));
  align-content: flex-start;
  gap: 8px;
}
.adapter-catalog__empty {
  grid-column: 1 / -1;
  padding: 24px 0;
}
</style>
