<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref, watch } from "vue"

import type { RowsView } from "@/client"
import { useConnectors } from "@/features/connectors/api"
import { GRANT_OPTIONS } from "@/features/connectors/access"
import type { Grant } from "@/features/connectors/access"
import {
  offerable,
  useDirectory,
  useGrants,
  useWriteGrant,
} from "@/features/connectors/grants"
import GrantList from "@/features/shares/GrantList.vue"
import { useCreateShare, useDeleteShare, useShares } from "@/features/shares/api"
import AccessRequests from "@/features/shares/AccessRequests.vue"
import { linkFor } from "@/features/shares/sharedView"
import { emptyRecipientsMessage } from "./recipients"
import { serverContext } from "@/shared/servers/context"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import {
  AppButton,
  AppBanner,
  AppCopyButton,
  AppIconButton,
  AppInput,
  AppForm,
  AppSelect,
  AppSpinner,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * One dialog for both halves of sharing: the address, and who may follow it.
 *
 * The link carries no rights (D58), so everybody who can reach the connection
 * sees it; grants are the owner's business (D33), so the rest appears for them
 * alone. Opened from a tab with a view to share and from the connection's own
 * window without one — the link section is what differs.
 */
const props = defineProps<{
  modelValue: boolean
  connectorId: string
  /** The node this tab is showing. Absent when the dialog is about the connection. */
  nodeId?: string
  nodeLabel?: string
  view?: RowsView
}>()

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()

const toast = useToast()
const open = computed(() => props.modelValue)
const connectorId = computed(() => (props.modelValue ? props.connectorId : null))

const connectors = useConnectors()
const connector = computed(() =>
  (connectors.data.value?.data ?? []).find((row) => row.id === props.connectorId)
)
const connectorName = computed(() => connector.value?.name ?? "this connection")
const isOwner = computed(() => connector.value?.access === "own")

const grants = useGrants(computed(() => (isOwner.value ? connectorId.value : null)))
const directory = useDirectory(computed(() => open.value && isOwner.value))
const writeGrant = useWriteGrant(connectorId)

const shares = useShares(connectorId)
const createShare = useCreateShare(connectorId)
const deleteShare = useDeleteShare(connectorId)

const pickedUser = ref<string | null>(null)
const pickedLevel = ref<Grant>("read")
const token = ref<string | null>(null)
const linkError = ref("")

// A closed dialog keeps nothing: reopening it on another connection with a
// name still in the box would offer to share the wrong thing.
watch(open, (isOpen) => {
  if (!isOpen) {
    pickedUser.value = null
    pickedLevel.value = "read"
    token.value = null
    linkError.value = ""
  }
})

/**
 * The address for this view, made when the dialog opens.
 *
 * Pressing Share is the request; making a link hands nothing over and the same
 * view always answers with the same record (D59), so there is nothing to
 * confirm and nothing to press twice.
 */
watch(
  [open, () => props.nodeId, () => props.view],
  async ([isOpen, nodeId, view]) => {
    if (!isOpen || nodeId === undefined || view === undefined) return
    if (token.value !== null || createShare.isPending.value) return
    try {
      const made = await createShare.mutateAsync({
        connector_id: props.connectorId,
        node_id: nodeId,
        node_label: props.nodeLabel ?? nodeId,
        view,
      })
      token.value = made.token
    } catch (error) {
      linkError.value = messageOf(error, "This link could not be made")
    }
  },
  { immediate: true }
)

const link = computed(() =>
  token.value === null ? "" : linkFor(token.value, window.location.origin, serverContext().active.url)
)

const held = computed(() => grants.data.value?.data ?? [])

const candidates = computed(() =>
  offerable(directory.data.value?.data ?? [], held.value).map((user) => ({
    label: user.full_name ? `${user.full_name} (${user.email})` : user.email,
    value: user.id,
  }))
)

const recipientsFailed = computed(() => directory.isError.value || grants.isError.value)
const recipientsReady = computed(() => directory.isSuccess.value && grants.isSuccess.value)
const recipientsMessage = computed(() => recipientsReady.value && !recipientsFailed.value
  ? emptyRecipientsMessage(directory.data.value?.data.length ?? 0, candidates.value.length)
  : ""
)

async function retryRecipients() {
  await Promise.all([directory.refetch(), grants.refetch()])
}

/** Every other link to this connection: the one just made has its own place. */
const otherLinks = computed(() =>
  (shares.data.value?.data ?? []).filter((share) => share.token !== token.value)
)

const loading = computed(
  () => grants.isLoading.value || directory.isLoading.value || shares.isLoading.value
)

function openersOf(openers: { email: string; opens: number }[]): string {
  if (openers.length === 0) return "Not opened yet"
  return `Opened by ${openers.map((opener) => opener.email).join(", ")}`
}

async function copyLink() {
  try {
    await copyText(link.value)
    toast.success("Link copied")
  } catch {
    toast.error("This browser would not let the link be copied")
  }
}

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

async function forget(shareId: string) {
  try {
    await deleteShare.mutateAsync(shareId)
    if (shares.data.value?.data.find((one) => one.id === shareId)?.token === token.value) {
      token.value = null
    }
  } catch (error) {
    toast.error(messageOf(error, "That link could not be deleted"))
  }
}
</script>

<template>
  <!--
    A floating window rather than a modal: everything else opened from a tab is
    one, and the point of it here is the same as everywhere — the link and the
    grid it was made from can be looked at together. See D14.
  -->
  <WindowDialog
    :model-value="modelValue"
    :title="`Share — ${nodeLabel ?? connectorName}`"
    size="form"
    sizing="stable"
    data-testid="share-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="share">
      <AppSpinner v-if="loading" />

      <template v-else>
        <AppForm
          v-if="nodeId !== undefined"
          class="share__link"
        >
          <AppSpinner v-if="createShare.isPending.value" />
          <p
            v-else-if="linkError"
            class="share__error"
            data-testid="share-link-error"
          >
            {{ linkError }}
          </p>
          <template v-else>
            <AppInput
              :model-value="link"
              label="Link to this view"
              readonly
              data-testid="share-link"
            >
              <template #after>
                <AppCopyButton
                  tooltip="Copy this link"
                  data-testid="share-copy"
                  @click="copyLink"
                />
              </template>
            </AppInput>
            <p class="share__note">
              Anyone signed in who has access to {{ connectorName }} opens the same
              rows with the same filters. Anyone else is shown what it is and who
              shared it, and nothing more.
            </p>
          </template>
        </AppForm>

        <template v-if="isOwner">
          <AppForm class="share__add">
            <AppBanner
              v-if="recipientsFailed"
              tone="error"
              data-testid="share-recipients-error"
            >
              Could not load recipients and their access. Try again.
              <AppButton
                label="Retry"
                variant="quiet"
                :loading="directory.isFetching.value || grants.isFetching.value"
                @click="retryRecipients"
              />
            </AppBanner>
            <p
              v-else-if="recipientsMessage"
              class="share__note"
              role="status"
              data-testid="share-recipients-empty"
            >
              {{ recipientsMessage }}
            </p>
            <AppSelect
              v-model="pickedUser"
              label="Person"
              data-testid="share-user"
              :options="candidates"
              :disable="!recipientsReady || recipientsFailed || candidates.length === 0"
            />
            <AppSelect
              v-model="pickedLevel"
              label="May"
              data-testid="share-level"
              :options="GRANT_OPTIONS"
            >
              <template #after>
                <AppButton
                  label="Give access"
                  data-testid="share-submit"
                  :disable="!recipientsReady || recipientsFailed || !candidates.some((candidate) => candidate.value === pickedUser)"
                  :loading="writeGrant.isPending.value"
                  @click="share"
                />
              </template>
            </AppSelect>

            <p class="share__note">
              Access is to the whole connection {{ connectorName }}, not only to
              {{ nodeLabel ?? "this node" }}.
            </p>
          </AppForm>

          <!-- Only where there is no page already showing it: opened from
               the connection's own window, the list is behind this dialog and
               a second copy of it would be a second answer (D33). -->
          <GrantList
            v-if="nodeId !== undefined"
            :connector-id="connectorId"
          />
        </template>

        <!-- Where there is no page showing them: from a tab this dialog is
             the only place the owner has, and from the connection's own
             window they are on the page behind it (D61). -->
        <AccessRequests
          v-if="isOwner && nodeId !== undefined"
          :connector-id="connectorId"
        />

        <section
          v-if="otherLinks.length > 0"
          class="share__links"
        >
          <h3 class="share__heading">
            Other links to this connection
          </h3>
          <ul
            class="share__list"
            data-testid="share-links"
          >
            <li
              v-for="other in otherLinks"
              :key="other.id"
              class="share__row"
              :data-testid="`share-link-${other.id}`"
            >
              <span class="share__who">
                <span class="share__name">{{ other.node_label }}</span>
                <span class="share__email">
                  {{ other.shared_by }} — {{ openersOf(other.openers ?? []) }}
                </span>
              </span>
              <AppIconButton
                v-if="other.can_delete"
                :icon="appIcons.close"
                variant="danger-quiet"
                tooltip="Delete this link. It does not take anybody's access away."
                :data-testid="`share-forget-${other.id}`"
                @click="forget(other.id)"
              />
            </li>
          </ul>
        </section>
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
  </WindowDialog>
</template>

<style scoped>
.share {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-4);
  padding: var(--dp-space-4);
}
.share__link,
.share__links {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}
.share__heading {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--dp-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.share__note {
  margin: 0;
  font-size: 12px;
  color: var(--dp-text-muted);
}
.share__error {
  margin: 0;
  font-size: 12px;
  color: var(--dp-content-error);
}
.share__add {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-4);
}
.share__links {
  border-top: 1px solid var(--dp-border);
  padding-top: var(--dp-space-3);
}
.share__list {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-half);
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
