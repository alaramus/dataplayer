<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref, watch } from "vue"

import type { DashboardPublic } from "@/client"
import { offerable, useDirectory } from "@/features/connectors/grants"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import { serverContext } from "@/shared/servers/context"
import {
  AppButton,
  AppCopyButton,
  AppEmptyState,
  AppForm,
  AppIconButton,
  AppInput,
  AppSelect,
  AppSpinner,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useDashboardGrants, useRevokeDashboardGrant, useWriteDashboardGrant } from "./api"
import { DASHBOARD_LEVELS, dashboardLinkFor, mayManage } from "./sharing"
import type { DashboardLevel } from "./sharing"

/**
 * Who may see a dashboard, and its address (D129). The address carries no
 * right: it opens the dashboard for whoever already has standing on it, and
 * the people are given standing here, by its owner alone.
 */
const open = defineModel<boolean>({ required: true })
const props = defineProps<{ dashboard: DashboardPublic }>()

const toast = useToast()
const owner = computed(() => mayManage(props.dashboard))
const dashboardId = computed(() => props.dashboard.id)
const grants = useDashboardGrants(computed(() => (open.value && owner.value ? props.dashboard.id : null)))
const directory = useDirectory(computed(() => open.value && owner.value))
const writing = useWriteDashboardGrant(dashboardId)
const revoking = useRevokeDashboardGrant(dashboardId)

const pickedUser = ref<string | null>(null)
const pickedLevel = ref<DashboardLevel>("read")

// A closed window keeps nothing, so reopening it on another dashboard offers
// nobody picked for this one.
watch(open, (isOpen) => {
  if (!isOpen) {
    pickedUser.value = null
    pickedLevel.value = "read"
  }
})

const link = computed(() => dashboardLinkFor(props.dashboard.id, window.location.origin, serverContext().active.url))
const held = computed(() => grants.data.value ?? [])
const candidates = computed(() =>
  offerable(directory.data.value?.data ?? [], held.value).map((user) => ({
    label: user.full_name ? `${user.full_name} (${user.email})` : user.email,
    value: user.id,
  }))
)

async function copyLink() {
  try {
    await copyText(link.value)
    toast.success("Link copied")
  } catch {
    toast.error("This browser would not let the link be copied")
  }
}

async function give() {
  if (pickedUser.value === null) return
  try {
    await writing.mutateAsync({ user_id: pickedUser.value, access: pickedLevel.value })
    pickedUser.value = null
    pickedLevel.value = "read"
  } catch (cause) {
    toast.error(messageOf(cause, "That access could not be given"))
  }
}

async function change(userId: string, level: unknown) {
  try {
    await writing.mutateAsync({ user_id: userId, access: level as DashboardLevel })
  } catch (cause) {
    toast.error(messageOf(cause, "That access could not be changed"))
  }
}

async function revoke(userId: string) {
  try {
    await revoking.mutateAsync(userId)
  } catch (cause) {
    toast.error(messageOf(cause, "That access could not be taken away"))
  }
}
</script>

<template>
  <WindowDialog
    v-model="open"
    :title="`Share — ${dashboard.name}`"
    size="form"
    sizing="stable"
    data-testid="dashboard-share-dialog"
  >
    <div class="dashboard-share">
      <AppForm class="dashboard-share__form">
        <AppInput
          :model-value="link"
          label="Link to this dashboard"
          readonly
          data-testid="dashboard-share-link"
        >
          <template #after>
            <AppCopyButton
              tooltip="Copy this link"
              @click="copyLink"
            />
          </template>
        </AppInput>
        <p class="dashboard-share__note">
          It opens the dashboard for anybody who has been given access to it, and
          for nobody else.
        </p>
      </AppForm>

      <template v-if="owner">
        <AppForm class="dashboard-share__form">
          <AppSelect
            v-model="pickedUser"
            label="Person"
            :options="candidates"
            :disable="!directory.isSuccess.value || candidates.length === 0"
            data-testid="dashboard-share-user"
          />
          <AppSelect
            v-model="pickedLevel"
            label="May"
            :options="DASHBOARD_LEVELS"
            data-testid="dashboard-share-level"
          >
            <template #after>
              <AppButton
                label="Give access"
                :disable="pickedUser === null"
                :loading="writing.isPending.value"
                data-testid="dashboard-share-submit"
                @click="give"
              />
            </template>
          </AppSelect>
          <p
            class="dashboard-share__note"
            data-testid="dashboard-share-warning"
          >
            Whoever is given access sees every series on this dashboard, your agents'
            hosts included, which they cannot see any other way. They do not see your
            other dashboards, agents or connections. Somebody who can edit adds only
            series they can read themselves.
          </p>
        </AppForm>

        <AppSpinner v-if="grants.isLoading.value" />
        <AppEmptyState
          v-else-if="held.length === 0"
          text="Nobody else can see this dashboard"
        />
        <ul
          v-else
          class="dashboard-share__list"
          data-testid="dashboard-share-grants"
        >
          <li
            v-for="grant in held"
            :key="grant.user_id"
            class="dashboard-share__row"
            :data-testid="`dashboard-grant-${grant.email}`"
          >
            <span class="dashboard-share__who">{{ grant.full_name ? `${grant.full_name} (${grant.email})` : grant.email }}</span>
            <AppSelect
              :model-value="grant.access"
              class="dashboard-share__level"
              :options="DASHBOARD_LEVELS"
              compact
              :aria-label="`What ${grant.email} may do`"
              :data-testid="`dashboard-grant-level-${grant.email}`"
              @update:model-value="(level) => change(grant.user_id, level)"
            />
            <AppIconButton
              :icon="appIcons.close"
              variant="danger-quiet"
              :tooltip="`Take access away from ${grant.email}`"
              :data-testid="`dashboard-grant-revoke-${grant.email}`"
              @click="revoke(grant.user_id)"
            />
          </li>
        </ul>
      </template>

      <p
        v-else
        class="dashboard-share__note"
      >
        {{ dashboard.owner ?? "Its owner" }} shared this dashboard with you. Only they
        give access to it.
      </p>
    </div>

    <template #actions>
      <AppButton
        variant="quiet"
        label="Close"
        data-testid="dashboard-share-close"
        @click="open = false"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.dashboard-share,
.dashboard-share__form {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-4);
}
.dashboard-share {
  padding: var(--dp-space-4);
}
.dashboard-share__note {
  margin: 0;
  font-size: 12px;
  color: var(--dp-text-muted);
}

.dashboard-share__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}

.dashboard-share__who {
  flex: 1;
  min-width: 0;
}

.dashboard-share__who {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-share__level {
  width: 140px;
}

.dashboard-share__list {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
