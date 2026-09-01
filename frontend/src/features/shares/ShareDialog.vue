<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { RowsView } from "@/client"
import { useConnectors } from "@/features/connectors/api"
import { GRANT_OPTIONS } from "@/features/connectors/access"
import type { Grant } from "@/features/connectors/access"
import {
  offerable,
  useDirectory,
  useGrants,
  useRevokeGrant,
  useWriteGrant,
} from "@/features/connectors/grants"
import {
  useAccessRequests,
  useAnswerRequest,
  useCreateShare,
  useDeleteShare,
  useShares,
} from "@/features/shares/api"
import { linkFor } from "@/features/shares/sharedView"
import { messageOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import {
  AppButton,
  AppCopyButton,
  AppDialog,
  AppEmptyState,
  AppIconButton,
  AppInput,
  AppSelect,
  AppSpinner,
  useToast,
} from "@/shared/ui"

/**
 * One dialog for both halves of sharing: the address, and who may follow it.
 *
 * The link is an address and carries no rights (D58), so everybody who can
 * reach the connection sees it. Grants are the owner's business (D33), so the
 * rest of the dialog appears for them alone — and the owner's sequence is one
 * movement: copy the address, add the colleague.
 *
 * Opened from a tab with a view to share, and from the connection's own window
 * without one. The link section is what differs.
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
const revokeGrant = useRevokeGrant(connectorId)

const shares = useShares(connectorId)
const createShare = useCreateShare(connectorId)
const deleteShare = useDeleteShare(connectorId)
const requests = useAccessRequests(
  computed(() => (isOwner.value ? connectorId.value : null))
)
const answerRequest = useAnswerRequest(connectorId)

/** The level each waiting person would be given, until the owner says otherwise. */
const answerLevel = ref<Record<string, Grant>>({})

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
  token.value === null ? "" : linkFor(token.value, window.location.origin)
)

const held = computed(() => grants.data.value?.data ?? [])

const waiting = computed(() => requests.data.value?.data ?? [])

/**
 * Answer somebody: a level gives it, nothing declines it.
 *
 * Both are the same movement for the person waiting — they are told either way
 * — so they are one function rather than two that must stay in step.
 */
async function answer(requestId: string, access: Grant | null) {
  try {
    await answerRequest.mutateAsync({ requestId, access })
  } catch (error) {
    toast.error(messageOf(error, "That request could not be answered"))
  }
}

const candidates = computed(() =>
  offerable(directory.data.value?.data ?? [], held.value).map((user) => ({
    label: user.full_name ? `${user.full_name} (${user.email})` : user.email,
    value: user.id,
  }))
)

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
  <AppDialog
    :model-value="modelValue"
    title="Share"
    :subtitle="nodeLabel ?? connectorName"
    size="md"
    data-testid="share-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="share">
      <AppSpinner v-if="loading" />

      <template v-else>
        <section
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
        </section>

        <template v-if="isOwner">
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
              class="share__level share__level--with-action"
              label="May"
              data-testid="share-level"
              :options="GRANT_OPTIONS"
            >
              <template #after>
                <AppButton
                  label="Give access"
                  data-testid="share-submit"
                  :disable="pickedUser === null"
                  :loading="writeGrant.isPending.value"
                  @click="share"
                />
              </template>
            </AppSelect>
          </div>

          <p class="share__note">
            Access is to the whole connection {{ connectorName }}, not only to
            {{ nodeLabel ?? "this node" }}.
          </p>

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

        <section
          v-if="isOwner && waiting.length > 0"
          class="share__links"
        >
          <h3 class="share__heading">
            Waiting for an answer
          </h3>
          <ul
            class="share__list"
            data-testid="share-requests"
          >
            <li
              v-for="ask in waiting"
              :key="ask.id"
              class="share__row"
              :data-testid="`share-request-${ask.requester_email}`"
            >
              <span class="share__who">
                <span class="share__name">
                  {{ ask.requester_name ?? ask.requester_email }}
                </span>
                <span class="share__email">
                  asked for {{ ask.node_label ?? connectorName }}
                </span>
              </span>
              <AppSelect
                :model-value="answerLevel[ask.id] ?? 'read'"
                class="share__level"
                compact
                :options="GRANT_OPTIONS"
                :data-testid="`share-request-level-${ask.requester_email}`"
                @update:model-value="answerLevel[ask.id] = $event as Grant"
              />
              <AppButton
                label="Give access"
                size="sm"
                :loading="answerRequest.isPending.value"
                :data-testid="`share-approve-${ask.requester_email}`"
                @click="answer(ask.id, answerLevel[ask.id] ?? 'read')"
              />
              <AppIconButton
                icon="close"
                variant="danger-quiet"
                tooltip="Say no. They are told, without a reason."
                :data-testid="`share-decline-${ask.requester_email}`"
                @click="answer(ask.id, null)"
              />
            </li>
          </ul>
        </section>

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
                icon="close"
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
  </AppDialog>
</template>

<style scoped>
.share {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-3);
  padding: 0 var(--dp-space-3) var(--dp-space-2);
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
  color: var(--dp-negative);
}
.share__add {
  display: flex;
  align-items: flex-start;
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
/* The select keeps its 160px while QField's own `after` area holds the button.
   The action is deliberately inside the field so its vertical position does
   not include the error-message line below the control. */
.share__level--with-action {
  width: 240px;
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
