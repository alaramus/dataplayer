<script setup lang="ts">
import { computed, ref } from "vue"

import {
  AppActions,
  AppBadge,
  AppBanner,
  AppButton,
  AppCard,
  AppCardFrame,
  AppCardHead,
  AppColorPicker,
  AppCombobox,
  AppEmptyState,
  AppFieldButton,
  AppFileInput,
  AppForm,
  AppFormControl,
  AppFullscreenToggle,
  AppIconButton,
  AppInput,
  AppLayout,
  AppMenu,
  AppNumberInput,
  AppOption,
  AppPageHeader,
  AppPairs,
  AppPairsRow,
  AppPopup,
  AppProgress,
  AppRadioGroup,
  AppCheckbox,
  AppCopyButton,
  AppScrollArea,
  AppSection,
  AppSectionsLayout,
  AppSelect,
  AppSettingRow,
  AppSpinner,
  AppTable,
  AppTabs,
  AppTaskbar,
  AppTaskbarItem,
  AppThemeToggle,
  AppToggle,
  AppToolbarRule,
  AppTooltip,
  AppTree,
  appIcons,
  namedIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"
import type { ButtonVariant, MenuItem, SelectOption, Tone } from "@/shared/ui"
import type { TableColumns } from "@/shared/ui/AppTable.vue"

const BUTTON_VARIANTS: ButtonVariant[] = ["primary", "secondary", "chosen", "current", "danger", "danger-quiet", "quiet"]
const iconFilter = ref("")
const visibleIcons = computed(() => {
  const query = iconFilter.value.trim().toLowerCase()
  return namedIcons.filter(({ name, icon }) =>
    name.toLowerCase().includes(query) || icon.toLowerCase().includes(query)
  )
})
const MENU_ITEMS: MenuItem[] = [
  { name: "check", label: "Check connection", icon: appIcons.bolt },
  { name: "edit", label: "Edit", icon: appIcons.edit },
  {
    name: "away",
    label: "Not available here",
    icon: appIcons.block,
    disable: true,
    hint: "Tick a row to use this",
  },
  { name: "delete", label: "Delete", icon: appIcons.delete, danger: true },
]
const menuOpen = ref(false)
const popupOpen = ref(false)
const savedHistoryOpen = ref(false)
const searchText = ref("")
const savedEntries = ref<MenuItem[]>([
  { name: "pg_class", label: "pg_class", removeLabel: "Remove pg_class from history" },
  { name: "notes", label: "notes", removeLabel: "Remove notes from history" },
])

const TONES: Tone[] = ["error", "success", "warning", "info"]
// The window sizes a dialog opens at. A window is measured to its
// content afterwards, so these are a starting width and height.
const SIZES = ["sm", "md", "lg"] as const
type DialogSize = (typeof SIZES)[number]

const COLUMNS: TableColumns = [
  { name: "name", label: "Name", field: "name", align: "left", sortable: true },
  { name: "kind", label: "Kind", field: "kind", align: "left" },
]
const ROWS = [
  { name: "postgres-local", kind: "postgres" },
  { name: "my files", kind: "file" },
]

const confirm = useConfirm()
const toast = useToast()

const dialogSize = ref<DialogSize>("md")
const dialogOpen = ref(false)
const text = ref("localhost")
const secret = ref("")
const tabColor = ref<string | null>(null)
const broken = ref<number | null>(null)
const choice = ref<string | null>("postgres")
const groupedChoice = ref<string | null>("claude")
const KIT_SECTIONS = [
  { id: "general", title: "General", summary: "What every page of settings starts with", icon: appIcons.settings },
  { id: "keys", title: "Keys", summary: "A second section, one line in a list", icon: appIcons.sshKey },
] as const
const kitSection = ref<string>("general")
const plain = ref("prefer")
const several = ref<string[]>(["public"])
const flag = ref(true)
const rows = ref("page")
const place = ref("favorites")
const PLACES = [
  { value: "favorites", label: "Favorites", icon: appIcons.star },
  { value: "history", label: "History", icon: appIcons.history },
]
const PAIRS = ref([
  { source: "id", target: "id", include: true },
  { source: "display_name", target: "name", include: true },
  { source: "notes", target: "notes", include: false },
])
const ROW_SCOPES = [
  { label: "Current page", value: "page", description: "Rows 1–50 · 6 visible columns" },
  { label: "All matching rows", value: "all", description: "2 active filters · streamed rather than held in memory" },
  { label: "Selected rows", value: "selected", description: "Tick rows in the grid first", disable: true },
]
const OPTION_ROWS: SelectOption[] = [
  { label: "Tables", value: "heading", group: true },
  {
    label: "orders_2024",
    value: "orders",
    icon: appIcons.tableChart,
    labelRuns: [{ text: "orders", hit: true }, { text: "_2024", hit: false }],
    description: "public · local pg",
    actionIcon: appIcons.myLocation,
    actionLabel: "Show in catalog",
  },
  {
    label: "notes.md",
    value: "notes",
    icon: appIcons.notes,
    descriptionRuns: [
      { text: "… the ", hit: false },
      { text: "orders", hit: true },
      { text: " of last week", hit: false },
    ],
  },
]
const comboWords = ref("")
const comboOpen = ref(false)
const comboChip = ref<string | null>(null)
/** Rows the person may take out: a cross each, Delete on the active one, Clear on the heading. */
const comboRecent = ref(["orders", "users"])
const comboOptions = computed<SelectOption[]>(() => [
  ...(comboChip.value === null
    ? [{ label: "Search in local pg", value: "scope", icon: appIcons.search, offer: true }]
    : []),
  ...(comboRecent.value.length === 0
    ? []
    : [
        { label: "Recent searches", value: "recent", group: true, removeLabel: "Clear recent searches" },
        ...comboRecent.value.map((words) => ({
          label: words,
          value: `recent:${words}`,
          icon: appIcons.history,
          removeLabel: "Remove from recent searches",
        })),
      ]),
  ...OPTION_ROWS,
])

function removeCombo(value: string | number) {
  const key = String(value)
  comboRecent.value = key === "recent" ? [] : comboRecent.value.filter((words) => `recent:${words}` !== key)
}
const comboStatus = computed(() => (comboWords.value.trim() === "" ? "" : "Searched 3 places"))

function pickCombo(value: string | number) {
  if (value === "scope") {
    comboChip.value = "in local pg"
    return
  }
  comboOpen.value = false
  toast.info(`Opened ${String(value)}`)
}

const file = ref<File | null>(null)
const files = ref<File[]>([])
const loading = ref(false)

const treeNodes = [{ id: "public", label: "public", children: [{ id: "orders", label: "orders" }] }]
const treeExpanded = ref<string[]>(["public"])
const treeSelected = ref<string | null>(null)
const treeTicked = ref<string[]>(["orders"])

function openDialog(size: DialogSize) {
  dialogSize.value = size
  dialogOpen.value = true
}

async function ask() {
  const answer = await confirm({
    title: "Delete connection",
    message: 'The connection "postgres-local" will be deleted permanently.',
    confirmLabel: "Delete",
    danger: true,
  })
  if (answer) {
    toast.success("Confirmed")
  } else {
    toast.info("Cancelled")
  }
}

function flash() {
  loading.value = true
  window.setTimeout(() => {
    loading.value = false
  }, 1200)
}

function removeSavedEntry(name: string) {
  savedEntries.value = savedEntries.value.filter((item) => item.name !== name)
  if (savedEntries.value.length === 0) savedHistoryOpen.value = false
}
</script>

<template>
  <AppLayout>
    <AppPageHeader title="UI kit">
      <template #actions>
        <AppButton
          variant="secondary"
          label="Toast"
          @click="toast.success('Saved')"
        />
        <AppButton
          variant="secondary"
          label="Toast with a way out"
          @click="
            toast.offer('Ivan asked for access to prod-db', {
              label: 'Open',
              onClick: () => toast.success('Opened'),
            })
          "
        />
        <AppButton
          variant="danger"
          label="Confirm"
          @click="ask"
        />
      </template>
    </AppPageHeader>

    <AppBanner
      tone="info"
      class="ui-kit__card"
    >
      Every component of the kit, with every variant it offers. Rendered from the real components,
      so this page breaks when one of them does.
    </AppBanner>

    <AppCard
      size="lg"
      title="Buttons"
      class="ui-kit__card"
    >
      <AppSection>
        <div class="row items-center ui-kit__row">
          <AppButton
            v-for="variant in BUTTON_VARIANTS"
            :key="variant"
            :variant="variant"
            :label="variant"
          />
        </div>
        <div class="row items-center ui-kit__row ui-kit__row--spaced">
          <AppButton
            size="sm"
            label="small"
          />
          <AppButton
            label="with icon"
            :icon="appIcons.add"
          />
          <AppButton
            variant="quiet"
            layout="toolbar"
            :icon="appIcons.autorenew"
            label="30 s"
          />
          <AppButton
            variant="quiet"
            layout="navigation"
            label="On this page"
          />
          <!-- Which side the icon is on is part of what the button says: one
               before the label names the action, one after it points where
               the action goes. -->
          <AppButton
            label="next"
            :icon-right="appIcons.chevronRight"
          />
          <AppButton
            label="loading"
            :loading="loading"
            @click="flash"
          />
          <AppButton
            label="disabled"
            disable
          />
        </div>
        <div class="row items-center ui-kit__row ui-kit__row--spaced">
          <AppIconButton
            :icon="appIcons.accountTree"
            tooltip="Browse catalog"
          />
          <AppIconButton
            :icon="appIcons.edit"
            tooltip="Edit"
          />
          <AppIconButton
            :icon="appIcons.key"
            tooltip="Configured"
            active
          />
          <AppIconButton
            :icon="appIcons.mic"
            tooltip="Stop dictating"
            live
          />
          <AppIconButton
            :icon="appIcons.delete"
            tooltip="Delete"
            variant="danger-quiet"
          />
          <AppIconButton
            :icon="appIcons.block"
            tooltip="Not available here"
            disable
          />
          <AppIconButton
            :icon="appIcons.filterAlt"
            tooltip="Filters (2)"
          >
            <AppBadge
              corner
              label="2"
            />
          </AppIconButton>
          <AppCopyButton />
          <AppButton
            variant="secondary"
            label="Row actions"
            :icon="appIcons.moreVert"
            aria-haspopup="menu"
            :aria-expanded="menuOpen"
          >
            <AppMenu
              v-model="menuOpen"
              :items="MENU_ITEMS"
              @select="toast.success(`chose ${$event}`)"
            />
          </AppButton>
          <AppButton
            variant="secondary"
            label="Popup panel"
            :icon="appIcons.dashboard"
            aria-haspopup="dialog"
            :aria-expanded="popupOpen"
          >
            <AppPopup v-model="popupOpen">
              <div class="ui-kit__pad">
                A popup holds whatever is not a menu of actions.
              </div>
            </AppPopup>
          </AppButton>
          <span class="dp-helper ui-kit__note">
            hover for tooltips
            <AppTooltip>A tooltip attaches to whatever contains it.</AppTooltip>
          </span>
          <!-- The real ones, so this page turns over with the rest of the
               application when the theme is pressed. -->
          <AppThemeToggle />
          <AppFullscreenToggle />
        </div>
        <AppTabs
          v-model="place"
          :options="PLACES"
        />
        <div class="row items-center ui-kit__row--spaced">
          <AppIconButton
            :icon="appIcons.refresh"
            tooltip="Reload"
          />
          <AppIconButton
            :icon="appIcons.window"
            tooltip="Open in a window"
          />
          <AppToolbarRule />
          <AppIconButton
            :icon="appIcons.moreVert"
            tooltip="Actions"
          />
        </div>
      </AppSection>
    </AppCard>

    <AppCard
      size="lg"
      title="Application icons"
      class="ui-kit__card"
    >
      <AppSection>
        <p class="ui-kit__note">
          All {{ namedIcons.length }} named icons in Material Symbols Outlined at the 32 px toolbar control size.
        </p>
        <AppForm
          layout="section"
          class="ui-kit__icon-filter"
        >
          <AppInput
            v-model="iconFilter"
            label="Find an icon"
          />
        </AppForm>
        <div class="ui-kit__icon-grid">
          <div class="ui-kit__icon-heading">
            Icon name
          </div>
          <div class="ui-kit__icon-heading">
            Symbols Outlined
          </div>
          <template
            v-for="item in visibleIcons"
            :key="item.name"
          >
            <div><code>{{ item.name }}</code><br><small>{{ item.icon }}</small></div>
            <span class="ui-kit__icon-box"><span class="material-symbols-outlined">{{ item.icon }}</span></span>
          </template>
        </div>
      </AppSection>
    </AppCard>

    <AppCard
      size="lg"
      title="Messages"
      class="ui-kit__card"
    >
      <AppSection gutter>
        <AppBanner
          v-for="tone in TONES"
          :key="tone"
          :tone="tone"
        >
          The {{ tone }} tone reads the same wherever it appears.
        </AppBanner>
      </AppSection>
      <AppSection divided>
        <div class="row items-center ui-kit__row">
          <AppBadge
            v-for="tone in TONES"
            :key="tone"
            :tone="tone"
            :label="tone"
          />
          <AppButton
            variant="quiet"
            size="sm"
            :icon="appIcons.terminal"
            aria-label="A count on a rail button"
          >
            <AppBadge
              corner
              label="2"
            />
          </AppButton>
        </div>
      </AppSection>
      <AppSection divided>
        <AppEmptyState
          icon="inbox"
          text="Nothing to show"
        />
      </AppSection>
      <AppSection divided>
        <AppSpinner />
        <AppProgress
          label="Measured work"
          :value="0.45"
        />
        <AppProgress label="Unknown work" />
        <AppProgress
          label="Paused work"
          :value="0.65"
          paused
        />
      </AppSection>
      <AppSection divided>
        <div class="ui-kit__scroll">
          <AppScrollArea>
            <div
              v-for="line in 20"
              :key="line"
            >
              Row {{ line }}
            </div>
          </AppScrollArea>
        </div>
      </AppSection>
    </AppCard>

    <AppCard
      size="lg"
      title="Fields"
      class="ui-kit__card"
    >
      <AppSection gutter>
        <AppForm
          class="ui-kit__form"
          data-testid="form-composition"
        >
          <AppInput
            v-model="text"
            label="Host"
            hint="The name or address the server answers on. A hint long enough to wrap keeps the line of the one above it."
            data-testid="kit-hinted-field"
          />
          <AppNumberInput
            v-model="broken"
            label="Port"
            error="Enter a port"
          />
          <AppSelect
            v-model="plain"
            label="SSL mode"
            :options="['prefer', 'require']"
          />
          <AppFormControl>
            Prefer tries TLS first and falls back to a plain connection.
          </AppFormControl>
          <AppFileInput
            v-model="file"
            label="Key file"
          />
          <AppBanner tone="warning">
            Some rows prevent this change. Correct their values first.
          </AppBanner>
          <AppCheckbox
            :model-value="true"
            label="Allow empty values"
          />
          <AppRadioGroup
            v-model="rows"
            label="Rows"
            :options="ROW_SCOPES"
          />
          <AppInput
            model-value="postgresql://dataplayer@127.0.0.1:5432/demo"
            label="URL"
            readonly
            monospace
          >
            <template #after>
              <AppCopyButton tooltip="Copy the connection string" />
            </template>
          </AppInput>
          <AppPairs>
            <template #from>
              In the file
            </template>
            <template #to>
              Column in the new table
            </template>
            <template #extra>
              Type
            </template>
            <template #aside>
              2 of 3
            </template>
            <AppPairsRow
              v-for="pair in PAIRS"
              :key="pair.source"
              :idle="!pair.include"
            >
              <template #from>
                <AppToggle
                  v-model="pair.include"
                  :label="pair.source"
                />
              </template>
              <template #to>
                <AppInput
                  v-model="pair.target"
                  :aria-label="`Name for ${pair.source}`"
                  :disable="!pair.include"
                  compact
                />
              </template>
              <template #extra>
                <AppSelect
                  model-value="text"
                  :aria-label="`Type of ${pair.source}`"
                  :options="['text', 'integer']"
                  :disable="!pair.include"
                  compact
                />
              </template>
            </AppPairsRow>
          </AppPairs>
        </AppForm>
        <AppInput
          v-model="text"
          label="Host"
        >
          <template #after>
            <AppColorPicker
              v-model="tabColor"
              label="Tab color"
            />
          </template>
        </AppInput>
        <AppInput
          v-model="secret"
          label="Password"
          type="password"
          placeholder="Leave unchanged"
        />
        <AppInput
          v-model="searchText"
          clearable
          placeholder="Search"
          autocomplete="off"
          @focus="savedHistoryOpen = savedEntries.length > 0"
          @click="savedHistoryOpen = savedEntries.length > 0"
          @blur="savedHistoryOpen = false"
          @keydown.esc="savedHistoryOpen = false"
          @keydown.tab="savedHistoryOpen = false"
          @keyup.enter="savedHistoryOpen = false"
        >
          <AppMenu
            v-model="savedHistoryOpen"
            :items="savedEntries"
            no-parent-event
            no-focus
            no-refocus
            fit
            @mousedown.prevent
            @select="searchText = $event"
            @remove="removeSavedEntry"
          />
          <template #prepend>
            <q-icon name="search" />
          </template>
        </AppInput>
        <AppNumberInput
          v-model="broken"
          label="Port"
          error="Must be a number between 1 and 65535"
        />
        <AppSelect
          v-model="choice"
          label="Source type"
          :options="[
            { label: 'PostgreSQL', value: 'postgres' },
            { label: 'Files', value: 'file' },
          ]"
        />
        <AppSelect
          v-model="groupedChoice"
          label="Grouped choices with actions"
          :options="[
            { label: 'Anthropic', value: 'provider:anthropic', group: true, description: 'A heading may say more, and carry its own action', actionIcon: 'key', actionLabel: 'Manage Anthropic API key', actionActive: true },
            { label: 'Claude', value: 'claude', description: 'API key set', actionIcon: 'key', actionLabel: 'Manage Anthropic API key', actionActive: true, stateIcon: 'key', stateActive: true },
            { label: 'OpenAI', value: 'provider:openai', group: true, separator: true },
            { label: 'GPT', value: 'gpt', description: 'API key required', actionIcon: 'key_off', actionLabel: 'Manage OpenAI API key', stateIcon: 'key_off' },
          ]"
          @option-action="toast.info($event.actionLabel ?? 'Option action')"
        />
        <AppSelect
          v-model="plain"
          label="SSL mode"
          :options="['disable', 'prefer', 'require']"
        />
        <AppSelect
          v-model="several"
          label="Schemas"
          summary-noun="Schemas"
          multiple
          compact
          :options="['public', 'sales', 'pg_catalog']"
        />
        <!-- A filter whose choices say what it is: named for a reader only. -->
        <AppSelect
          v-model="plain"
          label="SSL mode"
          label-hidden
          compact
          :options="['disable', 'prefer', 'require']"
        />
        <!-- The field of the search (D205): the list opens under the words
             without taking the focus, the arrows walk it, Enter with no row
             active submits, Escape closes the list and a second one leaves. -->
        <AppCombobox
          v-model="comboWords"
          v-model:open="comboOpen"
          class="ui-kit__combobox"
          label="Search the kit"
          placeholder="Search"
          :options="comboOptions"
          :status="comboStatus"
          :chip="comboChip"
          submit-label="Show all results"
          data-testid="kit-combobox"
          @pick="pickCombo"
          @action="toast.info(`Showed ${String($event)} in its catalog`)"
          @submit="toast.info(`Everything for “${comboWords}”`)"
          @remove-chip="comboChip = null"
          @remove="removeCombo"
        />
        <!-- What opens that field from a header: drawn as the field with its
             keys, and an icon alone once its room is narrower than the field.
             The second is given too little room on purpose. -->
        <div class="row items-center ui-kit__row">
          <AppFieldButton
            label="Search"
            :icon="appIcons.search"
            keys="Ctrl + K"
            keyshortcuts="Control+K"
            class="ui-kit__field-button"
            @click="toast.info('The search would open')"
          />
          <div class="ui-kit__narrow">
            <AppFieldButton
              label="Search"
              :icon="appIcons.search"
              keys="Ctrl + K"
              @click="toast.info('The search would open')"
            />
          </div>
        </div>
        <!-- One row of a list of choices, as AppSelect and AppCombobox draw
             it: the words that matched marked, never as HTML. -->
        <div class="ui-kit__options">
          <AppOption
            v-for="option in OPTION_ROWS"
            :key="String(option.value)"
            :option="option"
          />
        </div>
        <AppToggle
          v-model="flag"
          label="Recursive"
        />
        <AppCheckbox
          v-model="flag"
          label="Pick this one"
        />
        <AppCheckbox
          v-model="flag"
          label="Some of them"
          indeterminate
        />
        <AppRadioGroup
          v-model="rows"
          label="Rows"
          :options="ROW_SCOPES"
        />
        <AppFileInput
          v-model="file"
          label="File"
        />
        <AppFileInput
          v-model="files"
          label="Files"
          multiple
          append
        />
        <!-- The set listed by the screen instead, as the upload form lists
             it with sizes and a way to take one out. -->
        <AppFileInput
          v-model="files"
          label="Files, listed below"
          multiple
          append
          listed
        />
        <span>{{ files.map((picked) => picked.name).join(", ") || "Nothing chosen" }}</span>
      </AppSection>
    </AppCard>

    <AppCard
      size="lg"
      title="Table"
      class="ui-kit__card"
    >
      <AppSection>
        <!-- What the bar at the foot of the screen is made of: a window, and a
             section of the workspace put aside. -->
        <AppTaskbar label="What is open and not in front of you">
          <AppTaskbarItem
            title="Connection"
            :icon="appIcons.window"
            front
            close-label="Close Connection"
          />
          <AppTaskbarItem
            title="Navigation · 2"
            :icon="appIcons.accountTree"
            aside
          />
        </AppTaskbar>
      </AppSection>

      <AppSection>
        <AppTable
          :rows="ROWS"
          :columns="COLUMNS"
          row-key="name"
          compact
          :paged="false"
          empty-text="No connections yet"
        />
      </AppSection>
    </AppCard>

    <AppCard
      size="lg"
      title="Panels"
      class="ui-kit__card"
    >
      <AppSection>
        <div class="row items-center ui-kit__row">
          <AppButton
            v-for="size in SIZES"
            :key="size"
            variant="secondary"
            :label="`dialog ${size}`"
            @click="openDialog(size)"
          />
        </div>
      </AppSection>
      <AppActions align="left">
        <span class="dp-helper ui-kit__note">
          A footer is AppActions; inside a dialog it is the actions slot.
        </span>
      </AppActions>
    </AppCard>

    <AppCard
      size="lg"
      title="Sections and settings"
      subtitle="a page of sections beside its body, and one setting a row"
      class="ui-kit__card"
    >
      <AppSection>
        <AppSectionsLayout
          :sections="KIT_SECTIONS"
          :current="kitSection"
          testid="ui-kit-sections"
          @select="kitSection = $event"
        >
          <AppSettingRow
            title="Appearance"
            summary="The question on the left and its answer on the right."
          >
            <AppForm>
              <AppSelect
                v-model="choice"
                aria-label="Source type"
                :options="[
                  { label: 'PostgreSQL', value: 'postgres' },
                  { label: 'Files', value: 'file' },
                ]"
              />
            </AppForm>
          </AppSettingRow>
        </AppSectionsLayout>
      </AppSection>
    </AppCard>

    <AppCard
      size="lg"
      title="Cards"
      class="ui-kit__card"
    >
      <AppSection>
        <AppCardFrame
          tag="section"
        >
          <AppCardHead title="A card">
            <template #actions>
              <AppIconButton
                :icon="appIcons.add"
                tooltip="Add"
              />
            </template>
          </AppCardHead>
          <AppSection>
            A card of the working screens and its head: a Data section, a dashboard and a chat
            all stand in one.
          </AppSection>
        </AppCardFrame>
      </AppSection>
    </AppCard>

    <AppCard
      title="Tree"
      subtitle="the catalog tree, wrapped so screens ask the kit for it"
    >
      <AppSection>
        <AppTree
          v-model:expanded="treeExpanded"
          v-model:selected="treeSelected"
          :nodes="treeNodes"
          node-key="id"
        >
          <template #default-header="{ node }">
            <span>{{ node.label }}</span>
          </template>
        </AppTree>
      </AppSection>
      <AppSection divided>
        <AppTree
          v-model:expanded="treeExpanded"
          v-model:ticked="treeTicked"
          :nodes="treeNodes"
          :selected="null"
          node-key="id"
          tickable
        />
        <span>Ticked: {{ treeTicked.join(", ") || "nothing" }}</span>
      </AppSection>
    </AppCard>

    <WindowDialog
      v-model="dialogOpen"
      :size="dialogSize"
      title="A dialog"
      :subtitle="`size ${dialogSize}`"
    >
      <AppSection>
        The header, the body and the footer are the dialog's three slots. The body is whatever the
        screen puts there.
      </AppSection>
      <AppSection
        divided
        scroll
      >
        <div
          v-for="line in 30"
          :key="line"
        >
          A scrolling section stops the panel growing past the screen — line
          {{ line }}.
        </div>
      </AppSection>
      <template #actions>
        <AppButton
          variant="quiet"
          label="Cancel"
          @click="dialogOpen = false"
        />
        <AppButton
          label="Save"
          @click="dialogOpen = false"
        />
      </template>
    </WindowDialog>
  </AppLayout>
</template>

<style scoped>
.ui-kit__form {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-4);
}
.ui-kit__card {
  margin-bottom: var(--dp-space-4);
}
.ui-kit__row {
  gap: var(--dp-space-2);
}
.ui-kit__row--spaced {
  margin-top: var(--dp-space-4);
}
.ui-kit__pad {
  padding: var(--dp-space-2);
}
.ui-kit__combobox {
  max-width: 420px;
}
.ui-kit__field-button {
  max-width: 320px;
}
.ui-kit__narrow {
  display: flex;
  width: 120px;
}
.ui-kit__options {
  max-width: 420px;
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
}
/* A scroll area takes the height of what holds it. */
.ui-kit__scroll {
  display: flex;
  flex-direction: column;
  height: 120px;
  width: 160px;
}
.ui-kit__note {
  color: var(--dp-text-muted);
}
.ui-kit__icon-grid {
  display: grid;
  grid-template-columns: minmax(100px, 1fr) minmax(110px, 1fr);
  align-items: center;
  gap: var(--dp-space-2);
}
.ui-kit__icon-filter {
  max-width: 320px;
  margin-bottom: var(--dp-space-4);
}
.ui-kit__icon-grid small {
  color: var(--dp-text-muted);
}
.ui-kit__icon-heading {
  color: var(--dp-text-muted);
  font-weight: 600;
}
.ui-kit__icon-box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--dp-form-control-height);
  height: var(--dp-form-control-height);
}
.ui-kit__icon-box > span {
  font-size: var(--dp-icon-md);
}
</style>
