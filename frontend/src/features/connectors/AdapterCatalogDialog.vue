<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { AdapterTypeInfo, ServiceTemplateInfo } from "@/client"
import AdapterDetailPanel from "@/features/connectors/AdapterDetailPanel.vue"
import AdapterTile from "@/features/connectors/AdapterTile.vue"
import { ALL_CATEGORIES, categoryCounts, inFoundOrder } from "@/features/connectors/adapterSearch"
import { categoryIcon } from "@/features/connectors/adapters"
import { cardsOf, templatesOf } from "@/features/connectors/catalogCards"
import type { CatalogCard } from "@/features/connectors/catalogCards"
import { useAdapterTypes } from "@/features/connectors/api"
import { useServiceTemplates } from "@/features/services/api"
import { useProviderHits } from "@/features/search/useProviderHits"
import { t } from "@/shared/i18n"
import { AppButton, AppEmptyState, AppInput, AppSpinner, appIcons } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

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
  /** The type, and the card it was picked by: its name and picture (D264). */
  pick: [adapterType: string, card: { key: string; title: string }]
  start: [template: ServiceTemplateInfo]
  makeHere: [type: AdapterTypeInfo]
}>()

const adapterTypes = useAdapterTypes()
const serviceTemplates = useServiceTemplates()

const query = ref("")
const category = ref<string>(ALL_CATEGORIES)
const selectedKey = ref<string | null>(null)

const types = computed(() => adapterTypes.data.value ?? [])
// Counted by card: MySQL and MariaDB are two things to choose in SQL.
const categories = computed(() => categoryCounts(cardsOf(types.value).map((card) => card.type)))

/**
 * Searching is not filtering: a query is asked of every type there is, by the
 * search's own provider (D197), which also knows the services that start one.
 *
 * A search narrowed to the selected category would answer "nothing found" for
 * a type that is plainly there, which is the one answer a search must never
 * give wrongly. Until the first answer is in, the grid stays as it was.
 */
const { hits } = useProviderHits(query, "source_types")
const searching = computed(() => hits.value !== null)

const visible = computed<CatalogCard[]>(() => {
  if (hits.value !== null) {
    return cardsOf(
      inFoundOrder(
        types.value,
        hits.value.flatMap((hit) => (hit.target.kind === "object" ? [hit.target.object_id] : []))
      )
    )
  }
  if (category.value === ALL_CATEGORIES) return cardsOf(types.value)
  return cardsOf(types.value.filter((type) => type.category === category.value))
})

const selectedCard = computed(
  () => visible.value.find((card) => card.key === selectedKey.value) ?? null
)
const selected = computed(() => selectedCard.value?.type ?? null)

/** Everything this server offers to start, of any kind. */
const startable = computed<ServiceTemplateInfo[]>(() => serviceTemplates.data.value ?? [])

/**
 * The services of the selected kind, of which there may be more than one: a
 * PostgreSQL and a PostgreSQL with TimescaleDB in it are one source type and
 * two things to run (D119).
 */
const templates = computed(() =>
  selectedCard.value === null ? [] : templatesOf(selectedCard.value, startable.value)
)

// Reopened, the catalog starts where it started last time: a query left over
// from the previous visit would hide most of what there is to choose from.
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    query.value = ""
    category.value = ALL_CATEGORIES
    selectedKey.value = null
  }
)

function selectCategory(id: string) {
  query.value = ""
  category.value = id
}

function pick(card: CatalogCard) {
  emit("pick", card.type.name, { key: card.key, title: card.title })
}

function start(template: ServiceTemplateInfo) {
  emit("start", template)
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    size="wide-form"
    sizing="stable"
    :title="t('connectors.new_connection')"
    :subtitle="t('connectors.catalog_dialog.subtitle')"
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
            size="var(--dp-icon-sm)"
          />
          <span class="adapter-catalog__category-name">{{ row.title }}</span>
          <span class="adapter-catalog__count">{{ row.count }}</span>
        </div>
      </div>

      <div class="adapter-catalog__main">
        <AppInput
          v-model="query"
          clearable
          compact
          :prepend-icon="appIcons.search"
          :placeholder="t('connectors.catalog_dialog.search')"
          data-testid="adapter-search"
        />

        <AppSpinner v-if="adapterTypes.isLoading.value" />

        <div
          v-else
          class="adapter-catalog__grid"
        >
          <AdapterTile
            v-for="card in visible"
            :key="card.key"
            :card="card"
            :selected="card.key === selectedKey"
            @pick="selectedKey = card.key"
            @open="pick(card)"
          />

          <div
            v-if="visible.length === 0"
            class="adapter-catalog__empty"
          >
            <AppEmptyState
              icon="search_off"
              :text="t('connectors.catalog_dialog.no_match')"
            />
          </div>
        </div>
      </div>

      <AdapterDetailPanel
        :type="selected"
        :title="selectedCard?.title"
        :icon-key="selectedCard?.key"
        :templates="templates"
        @create="selectedCard && pick(selectedCard)"
        @start="start"
        @make-here="selected && emit('makeHere', selected)"
      />
    </div>

    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        @click="emit('update:modelValue', false)"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
/* The three columns fill the stable body and scroll inside it, rather than
   the window growing with the number of source types. */
.adapter-catalog {
  display: flex;
  min-height: 0;
  height: 100%;
  border-top: 1px solid var(--dp-border);
  border-bottom: 1px solid var(--dp-border);
}
.adapter-catalog__sidebar {
  flex: 0 1 auto;
  min-width: 0;
  width: clamp(150px, 22%, 220px);
  min-height: 0;
  overflow-y: auto;
  border-right: 1px solid var(--dp-border);
}
.adapter-catalog__category {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-2);
  cursor: pointer;
  min-width: 0;
}
.adapter-catalog__category:hover {
  background: var(--dp-hover);
}
/* Grey, as a chosen row is everywhere else: the chat in the history, the
   pressed button of a rail. */
.adapter-catalog__category--active,
.adapter-catalog__category--active:hover {
  background: var(--dp-tab-current);
  font-weight: 500;
}
/* Two lines before an ellipsis: a category's Russian name is half again
   the English one, and one line cut "Key–value stores" to its first word. */
.adapter-catalog__category-name {
  flex: 1;
  min-width: 0;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  line-height: var(--dp-line-height-sm);
}
.adapter-catalog__count {
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
}
.adapter-catalog__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  padding: var(--dp-space-3);
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
  gap: var(--dp-space-2);
}
.adapter-catalog__empty {
  grid-column: 1 / -1;
  padding: var(--dp-space-5) 0;
}
</style>
