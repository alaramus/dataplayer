<script setup lang="ts">
import { ref } from "vue"

import type { SshKeyPublic } from "@/client"
import SshKeyDialog from "@/features/sshKeys/SshKeyDialog.vue"
import UnlockKeyDialog from "@/features/sshKeys/UnlockKeyDialog.vue"
import { useDeleteSshKey, useLockSshKey, useSshKeys } from "@/features/sshKeys/api"
import { keyState, passphraseModeLabel } from "@/features/sshKeys/keys"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import {
  AppBadge,
  AppButton,
  AppCopyButton,
  AppEmptyState,
  AppIconButton,
  AppSpinner,
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
const unlocking = ref<SshKeyPublic | null>(null)

function usedBy(key: SshKeyPublic): string {
  if (key.used_by.length === 0) return "No connection uses it"
  return `Used by ${key.used_by.map((use) => use.name).join(", ")}`
}

async function copyPublic(key: SshKeyPublic) {
  await copyText(key.public_key)
  toast.success("Public key copied. Add it to authorized_keys on the server")
}

async function lock(key: SshKeyPublic) {
  try {
    await lockKey.mutateAsync(key.id)
  } catch (cause) {
    toast.error(messageOf(cause, "The key could not be locked"))
  }
}

async function remove(key: SshKeyPublic) {
  const sure = await confirm({
    title: "Delete this key?",
    message: `${key.name} will be gone from this server. Servers that trust its public half keep trusting it until you remove that line.`,
    confirmLabel: "Delete",
    danger: true,
  })
  if (!sure) return
  try {
    await removeKey.mutateAsync(key.id)
  } catch (cause) {
    toast.error(messageOf(cause, "The key could not be deleted"))
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
        <span class="ssh-keys__title">SSH keys</span>
        <span class="ssh-keys__summary">
          Keys your SSH connections sign in with. A key made here never leaves this
          server: copy its public key into authorized_keys on the servers it should
          open. A key that asks for its passphrase is kept locked, and opens for the
          time you choose when you type it.
        </span>
      </div>
      <div class="ssh-keys__buttons">
        <AppButton
          icon="add"
          label="New key"
          data-testid="ssh-key-new"
          @click="making = 'generate'"
        />
        <AppButton
          variant="quiet"
          icon="upload"
          label="Import"
          data-testid="ssh-key-import"
          @click="making = 'import'"
        />
      </div>
    </div>

    <AppSpinner v-if="keys.isLoading.value" />
    <AppEmptyState
      v-else-if="(keys.data.value ?? []).length === 0"
      icon="key"
      text="No SSH keys yet"
    />
    <div
      v-for="key in keys.data.value ?? []"
      :key="key.id"
      class="ssh-keys__row"
      :data-testid="`ssh-key-${key.name}`"
    >
      <q-icon
        name="key"
        size="18px"
      />
      <div class="ssh-keys__facts">
        <span class="ssh-keys__name">{{ key.name }}</span>
        <span class="ssh-keys__line">{{ key.algorithm }} · {{ key.fingerprint }}</span>
        <span class="ssh-keys__line">{{ passphraseModeLabel(key.passphrase_mode) }} · {{ usedBy(key) }}</span>
      </div>
      <AppBadge
        v-if="keyState(key)"
        :label="keyState(key)?.text ?? ''"
        :tone="keyState(key)?.open ? 'success' : 'warning'"
      />
      <AppCopyButton
        tooltip="Copy the public key"
        :data-testid="`ssh-key-copy-${key.name}`"
        @click="copyPublic(key)"
      />
      <AppIconButton
        v-if="keyState(key) && !keyState(key)?.open"
        icon="lock_open"
        tooltip="Unlock: type its passphrase"
        :data-testid="`ssh-key-unlock-${key.name}`"
        @click="unlocking = key"
      />
      <AppIconButton
        v-else-if="keyState(key)?.open"
        icon="lock"
        tooltip="Lock it now"
        :data-testid="`ssh-key-lock-${key.name}`"
        @click="lock(key)"
      />
      <AppIconButton
        icon="delete_outline"
        :tooltip="key.used_by.length ? 'Point its connections at another key first' : 'Delete this key'"
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
.ssh-keys__head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
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
.ssh-keys__summary,
.ssh-keys__line {
  color: var(--dp-text-muted);
  font-size: 12px;
  line-height: 1.5;
}
.ssh-keys__line {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ssh-keys__buttons {
  display: flex;
  gap: var(--dp-space-2);
}
.ssh-keys__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) 0;
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
