<script setup lang="ts">
import { ref } from "vue"

import {
  AppActions,
  AppBadge,
  AppBanner,
  AppButton,
  AppCard,
  AppEmptyState,
  AppFileInput,
  AppIconButton,
  AppInput,
  AppLayout,
  AppMenu,
  AppNumberInput,
  AppPageHeader,
  AppProgress,
  AppCheckbox,
  AppCopyButton,
  AppSection,
  AppSelect,
  AppSpinner,
  AppTable,
  AppThemeToggle,
  AppToggle,
  AppTooltip,
  AppTree,
  useConfirm,
  useToast,
} from "@/shared/ui"
import type { ButtonVariant, MenuItem, Tone } from "@/shared/ui"
import type { TableColumns } from "@/shared/ui/AppTable.vue"

const BUTTON_VARIANTS: ButtonVariant[] = [
  "primary",
  "secondary",
  "danger",
  "danger-quiet",
  "quiet",
]
const MENU_ITEMS: MenuItem[] = [
  { name: "check", label: "Check connection", icon: "bolt" },
  { name: "edit", label: "Edit", icon: "edit" },
  { name: "away", label: "Not available here", icon: "block", disable: true },
  { name: "delete", label: "Delete", icon: "delete", danger: true },
]
const menuOpen = ref(false)
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
const broken = ref<number | null>(null)
const choice = ref<string | null>("postgres")
const plain = ref("prefer")
const several = ref<string[]>(["public"])
const flag = ref(true)
const file = ref<File | null>(null)
const files = ref<File[]>([])
const loading = ref(false)

const treeNodes = [
  { id: "public", label: "public", children: [{ id: "orders", label: "orders" }] },
]
const treeExpanded = ref<string[]>(["public"])
const treeSelected = ref<string | null>(null)

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
      class="q-mb-md"
    >
      Every component of the kit, with every variant it offers. Rendered from
      the real components, so this page breaks when one of them does.
    </AppBanner>

    <AppCard
      size="lg"
      title="Buttons"
      class="q-mb-md"
    >
      <AppSection>
        <div class="row items-center q-gutter-sm">
          <AppButton
            v-for="variant in BUTTON_VARIANTS"
            :key="variant"
            :variant="variant"
            :label="variant"
          />
        </div>
        <div class="row items-center q-gutter-sm q-mt-md">
          <AppButton
            size="sm"
            label="small"
          />
          <AppButton
            label="with icon"
            icon="add"
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
        <div class="row items-center q-gutter-sm q-mt-md">
          <AppIconButton
            icon="account_tree"
            tooltip="Browse catalog"
          />
          <AppIconButton
            icon="edit"
            tooltip="Edit"
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
            label="Saved searches"
            icon="history"
            :disable="savedEntries.length === 0"
          >
            <AppMenu
              :items="savedEntries"
              @select="toast.success(`chose ${$event}`)"
              @remove="savedEntries = savedEntries.filter((item) => item.name !== $event)"
            />
          </AppButton>
          <span class="text-caption text-grey">
            hover for tooltips
            <AppTooltip>A tooltip attaches to whatever contains it.</AppTooltip>
          </span>
          <!-- The real one, so this page turns over with the rest of the
               application when it is pressed. -->
          <AppThemeToggle />
        </div>
      </AppSection>
    </AppCard>

    <AppCard
      size="lg"
      title="Messages"
      class="q-mb-md"
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
        <div class="row items-center q-gutter-sm">
          <AppBadge
            v-for="tone in TONES"
            :key="tone"
            :tone="tone"
            :label="tone"
          />
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
      class="q-mb-md"
    >
      <AppSection gutter>
        <AppInput
          v-model="text"
          label="Host"
        />
        <AppInput
          v-model="secret"
          label="Password"
          type="password"
          placeholder="Leave unchanged"
        />
        <AppInput
          v-model="text"
          clearable
          placeholder="Search"
        >
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
          v-model="plain"
          label="SSL mode"
          :options="['disable', 'prefer', 'require']"
        />
        <AppSelect
          v-model="several"
          label="Schemas"
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
      </AppSection>
    </AppCard>

    <AppCard
      size="lg"
      title="Table"
      class="q-mb-md"
    >
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
      class="q-mb-md"
    >
      <AppSection>
        <div class="row items-center q-gutter-sm">
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
        <span class="text-caption text-grey">
          A footer is AppActions; inside a dialog it is the actions slot.
        </span>
      </AppActions>
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
    </AppCard>

    <WindowDialog
      v-model="dialogOpen"
      :size="dialogSize"
      title="A dialog"
      :subtitle="`size ${dialogSize}`"
    >
      <AppSection>
        The header, the body and the footer are the dialog's three slots. The
        body is whatever the screen puts there.
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
