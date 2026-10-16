<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppButton, AppEmptyState, AppForm, AppSpinner, useConfirm, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useRemoveStore, useStoreUsage } from "./api"
import { originWording, removalWarning, sizeWording, tierWording } from "./storeFacts"

/**
 * The installation's metrics store, for a superuser: where it is, what it
 * takes, how long it keeps what, and taking it away (D126).
 */
const open = defineModel<boolean>({ required: true })

const toast = useToast()
const confirm = useConfirm()
const usage = useStoreUsage(open)
const removing = useRemoveStore()
const facts = computed(() => usage.data.value ?? null)

async function remove() {
  if (facts.value === null) return
  const sure = await confirm({
    title: t("dashboards.store.remove_title"),
    message: removalWarning(facts.value),
    confirmLabel: t("dashboards.common.remove_store"),
    danger: true,
  })
  if (!sure) return
  try {
    toast.success((await removing.mutateAsync()).message)
    open.value = false
  } catch (cause) {
    toast.error(messageOf(cause, t("dashboards.store.remove_failed")))
  }
}
</script>

<template>
  <WindowDialog
    v-model="open"
    :title="t('dashboards.store.title')"
    :subtitle="t('dashboards.store.subtitle')"
    size="compact-form"
    sizing="stable"
    data-testid="store-dialog"
  >
    <AppForm layout="section">
      <AppSpinner v-if="usage.isPending.value" />
      <AppEmptyState
        v-else-if="facts === null"
        icon="error"
        :text="messageOf(usage.error.value, t('dashboards.store.describe_failed'))"
      />
      <dl
        v-else
        class="store-facts"
      >
        <dt>{{ t('dashboards.store.where') }}</dt>
        <dd data-testid="store-origin">
          {{ originWording(facts) }}
        </dd>
        <dt>{{ t('dashboards.store.size') }}</dt>
        <dd data-testid="store-size">
          {{ sizeWording(facts) }}
        </dd>
        <dt>{{ t('dashboards.store.kept') }}</dt>
        <dd>
          <div
            v-for="tier in facts.tiers"
            :key="tier.name"
          >
            {{ tierWording(tier) }}
          </div>
        </dd>
      </dl>
    </AppForm>

    <template #actions>
      <AppButton
        variant="danger"
        :icon="appIcons.deleteForever"
        :label="t('dashboards.common.remove_store')"
        :disable="facts === null"
        :loading="removing.isPending.value"
        data-testid="store-remove"
        @click="remove"
      />
      <AppButton
        variant="quiet"
        :label="t('dashboards.common.close')"
        @click="open = false"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.store-facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--dp-space-2) var(--dp-space-4);
  margin: 0;
}

.store-facts dt {
  color: var(--dp-text-muted);
}

.store-facts dd {
  margin: 0;
}
</style>
