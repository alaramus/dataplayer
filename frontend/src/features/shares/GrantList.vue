<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { GRANT_OPTIONS } from "@/features/connectors/access"
import type { Grant } from "@/features/connectors/access"
import { useGrants, useRevokeGrant, useWriteGrant } from "@/features/connectors/grants"
import { messageOf } from "@/shared/api/errors"
import {
  AppEmptyState,
  AppIconButton,
  AppSelect,
  AppSpinner,
  useToast,
} from "@/shared/ui"

/**
 * Who holds a level on one connection, and what can be done about it.
 *
 * In two places — the connection's own window and the Share dialog — as one
 * component, because two copies of this list would be two answers to one
 * question and the second would be the stale one (D33). Only ever drawn for
 * the owner: asking for somebody else's grants is answered with 403.
 */
const props = defineProps<{ connectorId: string | null }>()

const toast = useToast()
const connectorId = computed(() => props.connectorId)
const grants = useGrants(connectorId)
const writeGrant = useWriteGrant(connectorId)
const revokeGrant = useRevokeGrant(connectorId)

const held = computed(() => grants.data.value?.data ?? [])

async function change(userId: string, level: Grant) {
  try {
    await writeGrant.mutateAsync({ user_id: userId, access: level })
  } catch (error) {
    toast.error(messageOf(error, "That access could not be changed"))
  }
}

async function revoke(userId: string) {
  try {
    await revokeGrant.mutateAsync(userId)
  } catch (error) {
    toast.error(messageOf(error, "That access could not be taken away"))
  }
}
</script>

<template>
  <AppSpinner v-if="grants.isLoading.value" />

  <AppEmptyState
    v-else-if="held.length === 0"
    text="Nobody else can reach this connection"
  />

  <ul
    v-else
    class="grants"
    data-testid="share-list"
  >
    <li
      v-for="grant in held"
      :key="grant.user_id"
      class="grants__row"
      :data-testid="`share-row-${grant.email}`"
    >
      <span class="grants__who">
        <span class="grants__name">{{ grant.full_name ?? grant.email }}</span>
        <span
          v-if="grant.full_name"
          class="grants__email"
        >
          {{ grant.email }}
        </span>
      </span>
      <AppSelect
        :model-value="grant.access"
        class="grants__level"
        compact
        :options="GRANT_OPTIONS"
        :data-testid="`share-level-${grant.email}`"
        @update:model-value="change(grant.user_id, $event as Grant)"
      />
      <AppIconButton
        :icon="appIcons.close"
        variant="danger-quiet"
        tooltip="Take this access away"
        :data-testid="`share-revoke-${grant.email}`"
        @click="revoke(grant.user_id)"
      />
    </li>
  </ul>
</template>

<style scoped>
.grants {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-half);
  margin: 0;
  padding: 0;
  list-style: none;
}
.grants__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}
.grants__who {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.grants__name,
.grants__email {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.grants__email {
  font-size: 12px;
  color: var(--dp-text-muted);
}
/* Wide enough for the longest wording in GRANT_OPTIONS, so the row does not
   change width as a level is chosen. */
.grants__level {
  width: 160px;
}
</style>
