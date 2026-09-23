<script setup lang="ts">
import { AxiosError } from "axios"
import { computed, ref, watch } from "vue"

import type { StoreStatus } from "@/client"
import { useAdapterTypes } from "@/features/connectors/api"
import { messageOf } from "@/shared/api/errors"
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
    toast.error(messageOf(cause, "TimescaleDB could not be started"))
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
    toast.error(messageOf(cause, "That database could not be used"))
  }
}
</script>

<template>
  <div
    class="store-setup"
    data-testid="store-setup"
  >
    <template v-if="stage.kind === 'offer'">
      <div class="text-h6">
        Dashboards need a metrics store
      </div>
      <p class="store-setup__text">
        Samples are kept in a TimescaleDB of their own, set up once for everybody on
        this server. Nobody reads it as a connection.
      </p>
      <div class="store-setup__actions">
        <span class="store-setup__slot">
          <AppButton
            icon="play_arrow"
            label="Start TimescaleDB on this server"
            :disable="!stage.canStart"
            :loading="starting.isPending.value"
            data-testid="store-start"
            @click="start"
          />
          <AppTooltip v-if="stage.startReason">{{ stage.startReason }}</AppTooltip>
        </span>
        <AppButton
          variant="secondary"
          icon="link"
          label="Connect an existing TimescaleDB"
          data-testid="store-connect"
          @click="connectOpen = true"
        />
      </div>
    </template>

    <template v-else-if="stage.kind === 'wait'">
      <div class="text-h6">
        Dashboards are not set up yet
      </div>
      <p class="store-setup__text">
        An administrator of this server sets up the store dashboards keep their samples in.
      </p>
    </template>

    <template v-else-if="stage.kind === 'starting'">
      <div class="text-h6">
        Starting the metrics store
      </div>
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
          icon="replay"
          label="Start it again"
          :loading="starting.isPending.value"
          @click="start"
        />
        <AppButton
          variant="secondary"
          icon="refresh"
          label="Ask again"
          @click="emit('retry')"
        />
        <AppButton
          v-if="stage.canRemove"
          variant="danger-quiet"
          icon="delete_forever"
          label="Remove the store"
          data-testid="store-open-removal"
          @click="storeOpen = true"
        />
      </div>
      <StoreDialog v-model="storeOpen" />
    </template>

    <WindowDialog
      v-model="connectOpen"
      title="Connect an existing TimescaleDB"
      subtitle="It is checked, and prepared with the schema metrics are kept in."
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
          label="Cancel"
          @click="connectOpen = false"
        />
        <AppButton
          label="Connect"
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
  max-width: 640px;
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
