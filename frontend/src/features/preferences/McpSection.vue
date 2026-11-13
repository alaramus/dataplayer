<script setup lang="ts">
import { computed, ref } from "vue"

import type { McpTokenPublic } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import { t } from "@/shared/i18n"
import { formatDate } from "@/shared/i18n/format"
import { serverUrl } from "@/shared/servers/context"
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

import McpTokenDialog from "./McpTokenDialog.vue"
import { useDeleteMcpToken, useMcpTokens } from "./api"
import { isExpired } from "./mcp"

/**
 * The tokens an agent outside DataPlayer enters `/mcp` with (D357, D358).
 * What is shown of a token is its name, its first characters and its dates;
 * the token itself was shown once, when it was made.
 */
const tokens = useMcpTokens()
const revoke = useDeleteMcpToken()
const toast = useToast()
const confirm = useConfirm()
const making = ref(false)

const address = computed(() => serverUrl("/mcp"))

function dates(token: McpTokenPublic): string {
  const made = t("preferences.mcp.created", { date: formatDate(token.created_at) })
  const ends = token.expires_at
    ? isExpired(token.expires_at)
      ? t("preferences.mcp.expired", { date: formatDate(token.expires_at) })
      : t("preferences.mcp.expires", { date: formatDate(token.expires_at) })
    : t("preferences.mcp.never_expires")
  const used = token.last_used_at
    ? t("preferences.mcp.last_used", { date: formatDate(token.last_used_at) })
    : t("preferences.mcp.never_used")
  return `${made} · ${ends} · ${used}`
}

async function copyAddress() {
  await copyText(address.value)
  toast.success(t("preferences.mcp.dialog.copied"))
}

async function remove(token: McpTokenPublic) {
  const sure = await confirm({
    title: t("preferences.mcp.revoke_title"),
    message: t("preferences.mcp.revoke_message", { name: token.name }),
    confirmLabel: t("preferences.mcp.revoke_confirm"),
    danger: true,
  })
  if (!sure) return
  try {
    await revoke.mutateAsync(token.id)
  } catch (cause) {
    toast.error(messageOf(cause, t("preferences.mcp.revoke_failed")))
  }
}
</script>

<template>
  <section
    class="mcp-tokens"
    data-testid="mcp-tokens"
  >
    <div class="mcp-tokens__head">
      <div class="mcp-tokens__what">
        <span class="mcp-tokens__title">{{ t('preferences.mcp.title') }}</span>
        <span class="dp-helper">{{ t('preferences.mcp.hint') }}</span>
        <div class="mcp-tokens__address">
          <span class="dp-helper">{{ t('preferences.mcp.address') }}</span>
          <code data-testid="mcp-address">{{ address }}</code>
          <AppCopyButton
            :tooltip="t('preferences.mcp.copy_address')"
            @click="copyAddress"
          />
        </div>
      </div>
      <div class="mcp-tokens__buttons">
        <AppButton
          size="sm"
          :icon="appIcons.add"
          :label="t('preferences.mcp.new_token')"
          data-testid="mcp-token-new"
          @click="making = true"
        />
      </div>
    </div>

    <AppSpinner v-if="tokens.isLoading.value" />
    <AppEmptyState
      v-else-if="(tokens.data.value ?? []).length === 0"
      :icon="appIcons.vpnKey"
      :text="t('preferences.mcp.empty')"
    />
    <div
      v-for="token in tokens.data.value ?? []"
      :key="token.id"
      class="mcp-tokens__row"
      :data-testid="`mcp-token-${token.name}`"
    >
      <q-icon
        :name="appIcons.vpnKey"
        size="var(--dp-icon-sm)"
      />
      <div class="mcp-tokens__facts">
        <span class="mcp-tokens__name">{{ token.name }}</span>
        <span class="mcp-tokens__line dp-helper">{{ token.shown }}… · {{ dates(token) }}</span>
      </div>
      <AppBadge
        v-if="isExpired(token.expires_at)"
        :label="t('preferences.mcp.expired_badge')"
        tone="warning"
      />
      <AppBadge
        :label="token.policy === 'full' ? t('preferences.mcp.full') : t('preferences.mcp.read_only')"
        :tone="token.policy === 'full' ? 'warning' : 'info'"
      />
      <AppIconButton
        :icon="appIcons.delete"
        :tooltip="t('preferences.mcp.revoke')"
        variant="danger-quiet"
        :data-testid="`mcp-token-revoke-${token.name}`"
        @click="remove(token)"
      />
    </div>

    <McpTokenDialog v-model="making" />
  </section>
</template>

<style scoped>
.mcp-tokens {
  display: flex;
  flex-direction: column;
  padding: var(--dp-space-4) 0;
  border-bottom: 1px solid var(--dp-border);
}
/* The column of controls is a setting row's, as in the SSH keys section. */
.mcp-tokens__head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--dp-side-column-width);
  gap: var(--dp-space-5);
  align-items: start;
  padding-bottom: var(--dp-space-4);
}
.mcp-tokens__what,
.mcp-tokens__facts {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
}
.mcp-tokens__facts {
  flex: 1;
  gap: var(--dp-space-half);
}
.mcp-tokens__title,
.mcp-tokens__name {
  font-weight: 500;
}
.mcp-tokens__address {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}
.mcp-tokens__address code {
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-mono);
  overflow-wrap: anywhere;
}
.mcp-tokens__line {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mcp-tokens__buttons {
  display: flex;
  gap: var(--dp-space-2);
}
.mcp-tokens__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) 0;
}
.mcp-tokens__row + .mcp-tokens__row {
  border-top: 1px solid var(--dp-border-faint);
}
</style>
