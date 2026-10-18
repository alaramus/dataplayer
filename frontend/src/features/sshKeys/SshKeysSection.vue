<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"
import { useRoute } from "vue-router"

import type { SshKeyPublic } from "@/client"
import SshKeyDialog from "@/features/sshKeys/SshKeyDialog.vue"
import UnlockKeyDialog from "@/features/sshKeys/UnlockKeyDialog.vue"
import { useDeleteSshKey, useLockSshKey, useSshKeys } from "@/features/sshKeys/api"
import { keyState, passphraseModeLabel } from "@/features/sshKeys/keys"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { copyText } from "@/shared/clipboard"
import {
  AppBadge,
  AppButton,
  AppCopyButton,
  AppEmptyState,
  AppIconButton,
  AppSpinner,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"

/**
 * The keys this person signs in to servers with (D146).
 *
 * What is shown of a key is what may be said out loud: its public half, to
 * copy onto a server, its fingerprint, and the connections that use it. The
 * private half was never sent back and there is nowhere here to see it.
 */
const keys = useSshKeys()
const removeKey = useDeleteSshKey()
const lockKey = useLockSshKey()
const toast = useToast()
const confirm = useConfirm()

const making = ref<"generate" | "import" | null>(null)

/** The key the search opened Preferences on (D205): scrolled to and marked. */
const route = useRoute()
const pointed = computed(() => (typeof route.query.key === "string" ? route.query.key : null))
watch(
  [pointed, () => keys.data.value],
  async ([id]) => {
    if (id === null) return
    await nextTick()
    document.querySelector(`[data-key-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "center" })
  },
  { immediate: true }
)
const unlocking = ref<SshKeyPublic | null>(null)

function usedBy(key: SshKeyPublic): string {
  if (key.used_by.length === 0) return t("ssh_keys.section.unused")
  return t("ssh_keys.section.used_by", { names: key.used_by.map((use) => use.name).join(", ") })
}

async function copyPublic(key: SshKeyPublic) {
  await copyText(key.public_key)
  toast.success(t("ssh_keys.section.public_copied"))
}

async function lock(key: SshKeyPublic) {
  try {
    await lockKey.mutateAsync(key.id)
  } catch (cause) {
    toast.error(messageOf(cause, t("ssh_keys.section.lock_failed")))
  }
}

async function remove(key: SshKeyPublic) {
  const sure = await confirm({
    title: t("ssh_keys.section.delete_title"),
    message: t("ssh_keys.section.delete_message", { name: key.name }),
    confirmLabel: t("ssh_keys.section.delete"),
    danger: true,
  })
  if (!sure) return
  try {
    await removeKey.mutateAsync(key.id)
  } catch (cause) {
    toast.error(messageOf(cause, t("ssh_keys.section.delete_failed")))
  }
}
</script>

<template>
  <section
    class="ssh-keys"
    data-testid="ssh-keys"
  >
    <div class="ssh-keys__head">
      <div class="ssh-keys__what">
        <span class="ssh-keys__title">{{ t('ssh_keys.section.title') }}</span>
        <span class="dp-helper">
          {{ t('ssh_keys.section.hint') }}
        </span>
      </div>
      <div class="ssh-keys__buttons">
        <AppButton
          :icon="appIcons.createSshKey"
          :label="t('ssh_keys.section.new_key')"
          data-testid="ssh-key-new"
          @click="making = 'generate'"
        />
        <AppButton
          variant="quiet"
          :icon="appIcons.importSshKey"
          :label="t('ssh_keys.section.import')"
          data-testid="ssh-key-import"
          @click="making = 'import'"
        />
      </div>
    </div>

    <AppSpinner v-if="keys.isLoading.value" />
    <AppEmptyState
      v-else-if="(keys.data.value ?? []).length === 0"
      :icon="appIcons.sshKey"
      :text="t('ssh_keys.section.empty')"
    />
    <div
      v-for="key in keys.data.value ?? []"
      :key="key.id"
      class="ssh-keys__row"
      :class="{ 'ssh-keys__row--pointed': key.id === pointed }"
      :data-key-id="key.id"
      :aria-current="key.id === pointed ? 'true' : undefined"
      :data-testid="`ssh-key-${key.name}`"
    >
      <q-icon
        :name="appIcons.sshKey"
        size="var(--dp-icon-sm)"
      />
      <div class="ssh-keys__facts">
        <span class="ssh-keys__name">{{ key.name }}</span>
        <span class="ssh-keys__line dp-helper">{{ key.algorithm }} · {{ key.fingerprint }}</span>
        <span class="ssh-keys__line dp-helper">{{ passphraseModeLabel(key.passphrase_mode) }} · {{ usedBy(key) }}</span>
      </div>
      <AppBadge
        v-if="keyState(key)"
        :label="keyState(key)?.text ?? ''"
        :tone="keyState(key)?.open ? 'success' : 'warning'"
      />
      <AppCopyButton
        :tooltip="t('ssh_keys.section.copy_public')"
        :data-testid="`ssh-key-copy-${key.name}`"
        @click="copyPublic(key)"
      />
      <AppIconButton
        v-if="keyState(key) && !keyState(key)?.open"
        :icon="appIcons.unlockSshKey"
        :tooltip="t('ssh_keys.section.unlock')"
        :data-testid="`ssh-key-unlock-${key.name}`"
        @click="unlocking = key"
      />
      <AppIconButton
        v-else-if="keyState(key)?.open"
        :icon="appIcons.lockSshKey"
        :tooltip="t('ssh_keys.section.lock')"
        :data-testid="`ssh-key-lock-${key.name}`"
        @click="lock(key)"
      />
      <AppIconButton
        :icon="appIcons.deleteSshKey"
        :tooltip="key.used_by.length ? t('ssh_keys.section.delete_used') : t('ssh_keys.section.delete_key')"
        :disable="key.used_by.length > 0"
        :data-testid="`ssh-key-delete-${key.name}`"
        @click="remove(key)"
      />
    </div>

    <SshKeyDialog
      :model-value="making !== null"
      :mode="making ?? 'generate'"
      @update:model-value="!$event && (making = null)"
    />
    <UnlockKeyDialog
      :key-id="unlocking?.id ?? null"
      :key-name="unlocking?.name ?? ''"
      @close="unlocking = null"
    />
  </section>
</template>

<style scoped>
.ssh-keys {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: var(--dp-space-4) 0;
  border-bottom: 1px solid var(--dp-border);
}
/* The column of controls is a setting row's (AppSettingRow), and the buttons
   start where its fields start. */
.ssh-keys__head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--dp-side-column-width);
  gap: var(--dp-space-5);
  align-items: start;
  padding-bottom: var(--dp-space-4);
}
.ssh-keys__what,
.ssh-keys__facts {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
}
.ssh-keys__facts {
  flex: 1;
  gap: var(--dp-space-half);
}
.ssh-keys__title,
.ssh-keys__name {
  font-weight: 500;
}
.ssh-keys__line {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Wrapped rather than squeezed: in the 260px side column the two Russian
   labels did not fit side by side, and a squeezed button stood its icon
   above its label. */
.ssh-keys__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
}
.ssh-keys__buttons > * {
  flex: none;
}
.ssh-keys__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) 0;
}
.ssh-keys__row--pointed {
  background: var(--dp-selected-quiet);
}
.ssh-keys__row + .ssh-keys__row {
  border-top: 1px solid var(--dp-border-faint);
}
@media (max-width: 700px) {
  .ssh-keys__head {
    grid-template-columns: 1fr;
  }
}
</style>
