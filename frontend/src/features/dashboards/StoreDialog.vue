<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { messageOf } from "@/shared/api/errors"
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
    title: "Remove the metrics store?",
    message: removalWarning(facts.value),
    confirmLabel: "Remove the store",
    danger: true,
  })
  if (!sure) return
  try {
    toast.success((await removing.mutateAsync()).message)
    open.value = false
  } catch (cause) {
    toast.error(messageOf(cause, "The metrics store could not be removed"))
  }
}
</script>

<template>
  <WindowDialog
    v-model="open"
    title="Metrics store"
    subtitle="Where every person's samples are kept"
    size="compact-form"
    sizing="stable"
    data-testid="store-dialog"
  >
    <AppForm layout="section">
      <AppSpinner v-if="usage.isPending.value" />
      <AppEmptyState
        v-else-if="facts === null"
        icon="error_outline"
        :text="messageOf(usage.error.value, 'The store could not be described')"
      />
      <dl
        v-else
        class="store-facts"
      >
        <dt>Where</dt>
        <dd data-testid="store-origin">
          {{ originWording(facts) }}
        </dd>
        <dt>Size</dt>
        <dd data-testid="store-size">
          {{ sizeWording(facts) }}
        </dd>
        <dt>Kept</dt>
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
        label="Remove the store"
        :disable="facts === null"
        :loading="removing.isPending.value"
        data-testid="store-remove"
        @click="remove"
      />
      <AppButton
        variant="quiet"
        label="Close"
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
