<script setup lang="ts">
import { ref } from "vue"

import type { CloudAccountPublic } from "@/client"
import CloudAccountDialog from "@/features/cloudAccounts/CloudAccountDialog.vue"
import { useCloudAccounts, useDeleteCloudAccount, useTestCloudAccount } from "@/features/cloudAccounts/api"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppBadge,
  AppButton,
  AppEmptyState,
  AppIconButton,
  AppSpinner,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"

/**
 * The cloud accounts this person's connections sign in with (D451).
 *
 * What is shown is what may be said out loud: the kind, how it signs in and
 * which connections use it. Secrets were never sent back.
 */
const accounts = useCloudAccounts()
const removeAccount = useDeleteCloudAccount()
const testAccount = useTestCloudAccount()
const toast = useToast()
const confirm = useConfirm()

/** The account the dialog changes; null makes a new one, undefined is closed. */
const editing = ref<CloudAccountPublic | null | undefined>(undefined)
const testing = ref<string | null>(null)

function usedBy(account: CloudAccountPublic): string {
  if (account.used_by.length === 0) return t("cloud_accounts.section.unused")
  return t("cloud_accounts.section.used_by", { names: account.used_by.map((use) => use.name).join(", ") })
}

async function test(account: CloudAccountPublic) {
  testing.value = account.id
  try {
    const found = await testAccount.mutateAsync(account.id)
    if (found.ok) toast.success(found.message)
    else toast.error(found.message)
  } catch (cause) {
    toast.error(messageOf(cause, t("cloud_accounts.section.test_failed")))
  } finally {
    testing.value = null
  }
}

async function remove(account: CloudAccountPublic) {
  const sure = await confirm({
    title: t("cloud_accounts.section.delete_title"),
    message: t("cloud_accounts.section.delete_message", { name: account.name }),
    confirmLabel: t("cloud_accounts.section.delete"),
    danger: true,
  })
  if (!sure) return
  try {
    await removeAccount.mutateAsync(account.id)
  } catch (cause) {
    toast.error(messageOf(cause, t("cloud_accounts.section.delete_failed")))
  }
}
</script>

<template>
  <section
    class="cloud-accounts"
    data-testid="cloud-accounts"
  >
    <div class="cloud-accounts__head">
      <div class="cloud-accounts__what">
        <span class="cloud-accounts__title">{{ t('cloud_accounts.section.title') }}</span>
        <span class="dp-helper">{{ t('cloud_accounts.section.hint') }}</span>
      </div>
      <div class="cloud-accounts__buttons">
        <AppButton
          size="sm"
          :icon="appIcons.add"
          :label="t('cloud_accounts.section.new_account')"
          data-testid="cloud-account-new"
          @click="editing = null"
        />
      </div>
    </div>

    <AppSpinner v-if="accounts.isLoading.value" />
    <AppEmptyState
      v-else-if="(accounts.data.value ?? []).length === 0"
      :icon="appIcons.cloud"
      :text="t('cloud_accounts.section.empty')"
    />
    <div
      v-for="account in accounts.data.value ?? []"
      :key="account.id"
      class="cloud-accounts__row"
      :data-testid="`cloud-account-${account.name}`"
    >
      <q-icon
        :name="appIcons.cloud"
        size="var(--dp-icon-sm)"
      />
      <div class="cloud-accounts__facts">
        <span class="cloud-accounts__name">{{ account.name }}</span>
        <span class="cloud-accounts__line dp-helper">{{ account.kind_title }} · {{ account.method_title }}</span>
        <span class="cloud-accounts__line dp-helper">{{ usedBy(account) }}</span>
      </div>
      <AppBadge
        v-if="account.ambient"
        :label="t('cloud_accounts.section.ambient')"
        tone="warning"
      />
      <AppIconButton
        v-if="account.testable"
        :icon="appIcons.playArrow"
        :tooltip="t('cloud_accounts.section.test')"
        :loading="testing === account.id"
        :data-testid="`cloud-account-test-${account.name}`"
        @click="test(account)"
      />
      <AppIconButton
        :icon="appIcons.edit"
        :tooltip="t('cloud_accounts.section.edit')"
        :data-testid="`cloud-account-edit-${account.name}`"
        @click="editing = account"
      />
      <AppIconButton
        :icon="appIcons.delete"
        :tooltip="account.used_by.length ? t('cloud_accounts.section.delete_used') : t('cloud_accounts.section.delete_account')"
        variant="danger-quiet"
        :disable="account.used_by.length > 0"
        :data-testid="`cloud-account-delete-${account.name}`"
        @click="remove(account)"
      />
    </div>

    <CloudAccountDialog
      :model-value="editing !== undefined"
      :account="editing ?? null"
      @update:model-value="!$event && (editing = undefined)"
    />
  </section>
</template>

<style scoped>
.cloud-accounts {
  display: flex;
  flex-direction: column;
  padding: var(--dp-space-4) 0;
  border-bottom: 1px solid var(--dp-border);
}
/* The column of controls is a setting row's (AppSettingRow), as SSH keys'. */
.cloud-accounts__head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--dp-side-column-width);
  gap: var(--dp-space-5);
  align-items: start;
  padding-bottom: var(--dp-space-4);
}
.cloud-accounts__what,
.cloud-accounts__facts {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
}
.cloud-accounts__facts {
  flex: 1;
  gap: var(--dp-space-half);
}
.cloud-accounts__title,
.cloud-accounts__name {
  font-weight: 500;
}
.cloud-accounts__line {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cloud-accounts__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
}
.cloud-accounts__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) 0;
}
.cloud-accounts__row + .cloud-accounts__row {
  border-top: 1px solid var(--dp-border-faint);
}
</style>
