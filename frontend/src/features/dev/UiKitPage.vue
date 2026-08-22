<script setup lang="ts">
import { ref } from "vue"

import {
  AppActions,
  AppBadge,
  AppBanner,
  AppButton,
  AppCard,
  AppDialog,
  AppEmptyState,
  AppFileInput,
  AppIconButton,
  AppInput,
  AppLayout,
  AppNumberInput,
  AppPageHeader,
  AppSection,
  AppSelect,
  AppSpinner,
  AppTable,
  AppToggle,
  AppTooltip,
  AppTree,
  useConfirm,
  useToast,
} from "@/shared/ui"
import type { ButtonVariant, PanelSize, Tone } from "@/shared/ui"
import type { TableColumns } from "@/shared/ui/AppTable.vue"

const BUTTON_VARIANTS: ButtonVariant[] = [
  "primary",
  "secondary",
  "danger",
  "danger-quiet",
  "quiet",
]
const TONES: Tone[] = ["error", "success", "warning", "info"]
const SIZES: PanelSize[] = ["xs", "sm", "md", "lg"]

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

const dialogSize = ref<PanelSize>("md")
const dialogOpen = ref(false)
const text = ref("localhost")
const secret = ref("")
const broken = ref<number | null>(null)
const choice = ref<string | null>("postgres")
const plain = ref("prefer")
const flag = ref(true)
const file = ref<File | null>(null)
const loading = ref(false)

const treeNodes = [
  { id: "public", label: "public", children: [{ id: "orders", label: "orders" }] },
]
const treeExpanded = ref<string[]>(["public"])
const treeSelected = ref<string | null>(null)

function openDialog(size: PanelSize) {
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
          <span class="text-caption text-grey">
            hover for tooltips
            <AppTooltip>A tooltip attaches to whatever contains it.</AppTooltip>
          </span>
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
        <AppToggle
          v-model="flag"
          label="Recursive"
        />
        <AppFileInput
          v-model="file"
          label="File"
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

    <AppDialog
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
    </AppDialog>
  </AppLayout>
</template>
