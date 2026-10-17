<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { AxiosError } from "axios"
import { computed, ref, watch } from "vue"

import type { StoreStatus } from "@/client"
import { useAdapterTypes } from "@/features/connectors/api"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import SchemaFields from "@/shared/SchemaForm/SchemaFields.vue"
import { readSchema } from "@/shared/SchemaForm/jsonSchema"
import type { JsonSchema } from "@/shared/SchemaForm/jsonSchema"
import { useSchemaForm } from "@/shared/SchemaForm/useSchemaForm"
import type { ServerError } from "@/shared/SchemaForm/useSchemaForm"
import { AppBanner, AppButton, AppForm, AppProgress, AppTooltip, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useConnectStore, useStartStore } from "./api"
import { setupStage } from "./setupStage"
import StoreDialog from "./StoreDialog.vue"

/**
 * What the dashboards say before there is a store to draw from (D126): a
 * superuser is offered the two ways to set one up, anybody else is told who
 * sets it up.
 */
const props = defineProps<{ status: StoreStatus }>()
const emit = defineEmits<{ retry: [] }>()

const toast = useToast()
const starting = useStartStore()
const connecting = useConnectStore()
const stage = computed(() => setupStage(props.status))

async function start() {
  try {
    await starting.mutateAsync()
  } catch (cause) {
    toast.error(messageOf(cause, t("dashboards.setup.start_failed")))
  }
}

const storeOpen = ref(false)

// Connecting: the PostgreSQL adapter's own fields, the user-and-password way.
const connectOpen = ref(false)
const adapterTypes = useAdapterTypes()
const form = useSchemaForm()
const fields = computed(() => {
  const postgres = (adapterTypes.data.value ?? []).find((type) => type.name === "postgres")
  if (postgres === undefined) return []
  const shape = readSchema(postgres.options_schema as JsonSchema)
  return shape.kind === "variants" ? (shape.byVariant.user_password ?? []) : shape.fields
})

watch(connectOpen, (isOpen) => {
  if (isOpen) form.reset(fields.value)
})
watch(fields, (next) => {
  if (connectOpen.value) form.reset(next, form.values.value)
})

async function connect() {
  try {
    await connecting.mutateAsync({ ...form.values.value, auth_method: "user_password" })
    connectOpen.value = false
  } catch (cause) {
    const detail: unknown = cause instanceof AxiosError ? cause.response?.data?.detail : undefined
    if (Array.isArray(detail)) {
      form.applyServerErrors(detail as ServerError[])
      return
    }
    toast.error(messageOf(cause, t("dashboards.setup.database_failed")))
  }
}
</script>

<template>
  <div
    class="store-setup"
    data-testid="store-setup"
  >
    <template v-if="stage.kind === 'offer'">
      <h2 class="dp-page-title">
        {{ t('dashboards.setup.offer_title') }}
      </h2>
      <p class="store-setup__text">
        {{ t('dashboards.setup.offer_text') }}
      </p>
      <div class="store-setup__actions">
        <span class="store-setup__slot">
          <AppButton
            :icon="appIcons.playArrow"
            :label="t('dashboards.setup.start')"
            :disable="!stage.canStart"
            :loading="starting.isPending.value"
            data-testid="store-start"
            @click="start"
          />
          <AppTooltip v-if="stage.startReason">{{ stage.startReason }}</AppTooltip>
        </span>
        <AppButton
          variant="secondary"
          :icon="appIcons.link"
          :label="t('dashboards.setup.connect_existing')"
          data-testid="store-connect"
          @click="connectOpen = true"
        />
      </div>
    </template>

    <template v-else-if="stage.kind === 'wait'">
      <h2 class="dp-page-title">
        {{ t('dashboards.setup.wait_title') }}
      </h2>
      <p class="store-setup__text">
        {{ t('dashboards.setup.wait_text') }}
      </p>
    </template>

    <template v-else-if="stage.kind === 'starting'">
      <h2 class="dp-page-title">
        {{ t('dashboards.setup.starting_title') }}
      </h2>
      <AppProgress
        :label="stage.step"
        :value="stage.progress"
        data-testid="store-progress"
      />
    </template>

    <template v-else>
      <AppBanner tone="error">
        {{ stage.message }}
      </AppBanner>
      <div class="store-setup__actions">
        <AppButton
          v-if="stage.canStart"
          :icon="appIcons.replay"
          :label="t('dashboards.setup.start_again')"
          :loading="starting.isPending.value"
          @click="start"
        />
        <AppButton
          variant="secondary"
          :icon="appIcons.refresh"
          :label="t('dashboards.setup.ask_again')"
          @click="emit('retry')"
        />
        <AppButton
          v-if="stage.canRemove"
          variant="danger-quiet"
          :icon="appIcons.deleteForever"
          :label="t('dashboards.common.remove_store')"
          data-testid="store-open-removal"
          @click="storeOpen = true"
        />
      </div>
      <StoreDialog v-model="storeOpen" />
    </template>

    <WindowDialog
      v-model="connectOpen"
      :title="t('dashboards.setup.connect_existing')"
      :subtitle="t('dashboards.setup.connect_subtitle')"
      size="form"
      sizing="stable"
      data-testid="store-connect-dialog"
    >
      <AppForm layout="section">
        <SchemaFields
          v-model="form.values.value"
          :fields="fields"
          :errors="form.errors.value"
        />
      </AppForm>
      <template #actions>
        <AppButton
          variant="quiet"
          :label="t('dashboards.common.cancel')"
          @click="connectOpen = false"
        />
        <AppButton
          :label="t('dashboards.setup.connect')"
          :loading="connecting.isPending.value"
          data-testid="store-connect-confirm"
          @click="connect"
        />
      </template>
    </WindowDialog>
  </div>
</template>

<style scoped>
.store-setup {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--dp-space-3);
  /* Wide enough for both offers on one row in a language longer than
     English: at the width of text (640px) the Russian pair stood one under
     the other, so it takes a page's. */
  max-width: var(--dp-page-max-width);
  margin: 10vh auto 0;
  padding: var(--dp-space-4);
}

.store-setup__text {
  margin: 0;
  color: var(--dp-text-muted);
}

.store-setup__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
}

.store-setup__slot {
  display: inline-flex;
}
</style>
