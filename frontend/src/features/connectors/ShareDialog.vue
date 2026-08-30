<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { GRANT_OPTIONS } from "@/features/connectors/access"
import type { Grant } from "@/features/connectors/access"
import {
  offerable,
  useDirectory,
  useGrants,
  useRevokeGrant,
  useWriteGrant,
} from "@/features/connectors/grants"
import { messageOf } from "@/shared/api/errors"
import {
  AppButton,
  AppDialog,
  AppEmptyState,
  AppIconButton,
  AppSelect,
  AppSpinner,
  useToast,
} from "@/shared/ui"

/**
 * Who else may reach this connection, and at what level.
 *
 * The owner's window only. What a level admits is stated here in words rather
 * than left to the name of the level: "structure" says nothing to somebody
 * deciding whether to hand a colleague a database.
 *
 * Nothing is confirmed twice. Lowering a level and taking it away are both
 * undone by setting it again, and a dialog that asked would be asking about a
 * change nobody can lose anything by. See D33.
 */
const props = defineProps<{
  modelValue: boolean
  connectorId: string
  connectorName: string
}>()

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()

const toast = useToast()
const open = computed(() => props.modelValue)
const connectorId = computed(() => (props.modelValue ? props.connectorId : null))

const grants = useGrants(connectorId)
const directory = useDirectory(open)
const writeGrant = useWriteGrant(connectorId)
const revokeGrant = useRevokeGrant(connectorId)

const pickedUser = ref<string | null>(null)
const pickedLevel = ref<Grant>("read")

// A closed dialog keeps nothing: reopening it on another connection with a
// name still in the box would offer to share the wrong thing.
watch(open, (isOpen) => {
  if (!isOpen) {
    pickedUser.value = null
    pickedLevel.value = "read"
  }
})

const held = computed(() => grants.data.value?.data ?? [])

const candidates = computed(() =>
  offerable(directory.data.value?.data ?? [], held.value).map((user) => ({
    label: user.full_name ? `${user.full_name} (${user.email})` : user.email,
    value: user.id,
  }))
)

const loading = computed(() => grants.isLoading.value || directory.isLoading.value)

async function share() {
  const userId = pickedUser.value
  if (userId === null) return
  try {
    await writeGrant.mutateAsync({ user_id: userId, access: pickedLevel.value })
    pickedUser.value = null
    pickedLevel.value = "read"
  } catch (error) {
    toast.error(messageOf(error, "That access could not be given"))
  }
}

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
  <AppDialog
    :model-value="modelValue"
    title="Share connection"
    :subtitle="connectorName"
    size="md"
    data-testid="share-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="share">
      <AppSpinner v-if="loading" />

      <template v-else>
        <div class="share__add">
          <AppSelect
            v-model="pickedUser"
            class="share__person"
            label="Person"
            data-testid="share-user"
            :options="candidates"
            :disable="candidates.length === 0"
          />
          <AppSelect
            v-model="pickedLevel"
            class="share__level"
            label="May"
            data-testid="share-level"
            :options="GRANT_OPTIONS"
          />
          <AppButton
            label="Share"
            data-testid="share-submit"
            :disable="pickedUser === null"
            :loading="writeGrant.isPending.value"
            @click="share"
          />
        </div>

        <AppEmptyState
          v-if="held.length === 0"
          text="Nobody else can reach this connection"
        />

        <ul
          v-else
          class="share__list"
          data-testid="share-list"
        >
          <li
            v-for="grant in held"
            :key="grant.user_id"
            class="share__row"
            :data-testid="`share-row-${grant.email}`"
          >
            <span class="share__who">
              <span class="share__name">{{ grant.full_name ?? grant.email }}</span>
              <span
                v-if="grant.full_name"
                class="share__email"
              >
                {{ grant.email }}
              </span>
            </span>
            <AppSelect
              :model-value="grant.access"
              class="share__level"
              compact
              :options="GRANT_OPTIONS"
              :data-testid="`share-level-${grant.email}`"
              @update:model-value="change(grant.user_id, $event as Grant)"
            />
            <AppIconButton
              icon="close"
              variant="danger-quiet"
              tooltip="Take this access away"
              :data-testid="`share-revoke-${grant.email}`"
              @click="revoke(grant.user_id)"
            />
          </li>
        </ul>
      </template>
    </div>

    <template #actions>
      <AppButton
        variant="quiet"
        label="Close"
        data-testid="share-close"
        @click="emit('update:modelValue', false)"
      />
    </template>
  </AppDialog>
</template>

<style scoped>
.share {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-3);
  padding: 0 var(--dp-space-3) var(--dp-space-2);
}
.share__add {
  display: flex;
  align-items: flex-end;
  gap: var(--dp-space-2);
}
.share__person {
  flex: 1;
  min-width: 0;
}
/* Wide enough for the longest wording in GRANT_OPTIONS, so the row does not
   change width as a level is chosen. */
.share__level {
  width: 160px;
}
.share__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.share__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}
.share__who {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.share__name,
.share__email {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.share__email {
  font-size: 12px;
  color: var(--dp-text-muted);
}
</style>
