<script setup lang="ts">
import { ref } from "vue"

import {
  AppActions,
  AppBadge,
  AppBanner,
  AppButton,
  AppCard,
  AppCardFrame,
  AppCardHead,
  AppColorPicker,
  AppEmptyState,
  AppFileInput,
  AppForm,
  AppFullscreenToggle,
  AppIconButton,
  AppInput,
  AppLayout,
  AppMenu,
  AppNumberInput,
  AppPageHeader,
  AppPopup,
  AppProgress,
  AppCheckbox,
  AppCopyButton,
  AppSection,
  AppSelect,
  AppSpinner,
  AppTable,
  AppTaskbar,
  AppTaskbarItem,
  AppThemeToggle,
  AppToggle,
  AppTooltip,
  AppTree,
  useConfirm,
  useToast,
} from "@/shared/ui"
import type { ButtonVariant, MenuItem, Tone } from "@/shared/ui"
import type { TableColumns } from "@/shared/ui/AppTable.vue"

const BUTTON_VARIANTS: ButtonVariant[] = ["primary", "secondary", "danger", "danger-quiet", "quiet"]
const MENU_ITEMS: MenuItem[] = [
  { name: "check", label: "Check connection", icon: "bolt" },
  { name: "edit", label: "Edit", icon: "edit" },
  {
    name: "away",
    label: "Not available here",
    icon: "block",
    disable: true,
    hint: "Tick a row to use this",
  },
  { name: "delete", label: "Delete", icon: "delete", danger: true },
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
const plain = ref("prefer")
const several = ref<string[]>(["public"])
const flag = ref(true)
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
            icon="add"
          />
          <AppButton
            variant="quiet"
            layout="toolbar"
            icon="autorenew"
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
            icon-right="chevron_right"
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
            icon="account_tree"
            tooltip="Browse catalog"
          />
          <AppIconButton
            icon="edit"
            tooltip="Edit"
          />
          <AppIconButton
            icon="key"
            tooltip="Configured"
            active
          />
          <AppIconButton
            icon="delete"
            tooltip="Delete"
            variant="danger-quiet"
          />
          <AppIconButton
            icon="block"
            tooltip="Not available here"
            disable
          />
          <AppCopyButton />
          <AppButton
            variant="secondary"
            label="Row actions"
            icon="more_vert"
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
            icon="dashboard"
            aria-haspopup="dialog"
            :aria-expanded="popupOpen"
          >
            <AppPopup v-model="popupOpen">
              <div class="ui-kit__pad">
                A popup holds whatever is not a menu of actions.
              </div>
            </AppPopup>
          </AppButton>
          <span class="text-caption ui-kit__note">
            hover for tooltips
            <AppTooltip>A tooltip attaches to whatever contains it.</AppTooltip>
          </span>
          <!-- The real ones, so this page turns over with the rest of the
               application when the theme is pressed. -->
          <AppThemeToggle />
          <AppFullscreenToggle />
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
            icon="terminal"
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
            { label: 'Anthropic', value: 'provider:anthropic', group: true },
            { label: 'Claude', value: 'claude', description: 'API key set', actionIcon: 'key', actionLabel: 'Manage Anthropic API key', actionActive: true, stateIcon: 'key', stateActive: true },
            { label: 'OpenAI', value: 'provider:openai', group: true },
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
            icon="web_asset"
            front
            close-label="Close Connection"
          />
          <AppTaskbarItem
            title="Navigation · 2"
            icon="account_tree"
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
        <span class="text-caption ui-kit__note">
          A footer is AppActions; inside a dialog it is the actions slot.
        </span>
      </AppActions>
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
                icon="add"
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
.ui-kit__note {
  color: var(--dp-text-muted);
}
</style>
