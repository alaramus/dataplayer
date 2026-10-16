<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import { GRANT_OPTIONS } from "@/features/connectors/access"
import type { Grant } from "@/features/connectors/access"
import { connectorNameOf, useConnectors } from "@/features/connectors/api"
import { useAccessRequests, useAnswerRequest } from "@/features/shares/api"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppButton, AppForm, AppIconButton, AppSelect, useToast } from "@/shared/ui"

/**
 * Who is waiting to be let in, and the answer. Beside the people who already
 * hold a level, because a request is answered by an ordinary grant and by
 * nothing else (D61). Nothing is drawn while nobody is waiting.
 *
 * The owner's alone: asking for the requests on somebody else's connection is
 * answered with 403.
 */
const props = defineProps<{ connectorId: string | null }>()

const toast = useToast()
const connectorId = computed(() => props.connectorId)
const requests = useAccessRequests(connectorId)
const answerRequest = useAnswerRequest(connectorId)
const connectors = useConnectors()

/**
 * What the connection is called now, for a request that named no node.
 *
 * Read from the list rather than taken as a prop: this is drawn inside a
 * window where the name is being edited, and what somebody asked for is the
 * connection as it stands, not as it is being renamed.
 */
const connectorName = computed(() => connectorNameOf(connectors.data.value, connectorId.value))

/** What somebody asked for: the node the link named, or the connection. */
function askedFor(nodeLabel: string | null | undefined): string {
  const name = nodeLabel ?? connectorName.value
  return t("shares.asking.asked_for", {
    what: name === null ? t("shares.to_this_connection") : t("shares.named", { name }),
  })
}

const waiting = computed(() => requests.data.value?.data ?? [])

/** The level each waiting person would be given, until the owner says otherwise. */
const answerLevel = ref<Record<string, Grant>>({})

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
    toast.error(messageOf(error, t("shares.asking.answer_failed")))
  }
}
</script>

<template>
  <section
    v-if="waiting.length > 0"
    class="asking"
  >
    <h3 class="asking__heading dp-overline">
      {{ t('shares.asking.heading') }}
    </h3>
    <ul
      class="asking__list"
      data-testid="share-requests"
    >
      <li
        v-for="ask in waiting"
        :key="ask.id"
        class="asking__row"
        :data-testid="`share-request-${ask.requester_email}`"
      >
        <span class="asking__who">
          <span class="asking__name">
            {{ ask.requester_name ?? ask.requester_email }}
          </span>
          <span class="asking__email">
            {{ askedFor(ask.node_label) }}
          </span>
        </span>
        <AppForm class="asking__level">
          <AppSelect
            :model-value="answerLevel[ask.id] ?? 'read'"
            compact
            :options="GRANT_OPTIONS"
            :data-testid="`share-request-level-${ask.requester_email}`"
            @update:model-value="answerLevel[ask.id] = $event as Grant"
          />
        </AppForm>
        <AppButton
          :label="t('shares.asking.give_access')"
          size="sm"
          :loading="answerRequest.isPending.value"
          :data-testid="`share-approve-${ask.requester_email}`"
          @click="answer(ask.id, answerLevel[ask.id] ?? 'read')"
        />
        <AppIconButton
          :icon="appIcons.close"
          variant="danger-quiet"
          :tooltip="t('shares.asking.decline')"
          :data-testid="`share-decline-${ask.requester_email}`"
          @click="answer(ask.id, null)"
        />
      </li>
    </ul>
  </section>
</template>

<style scoped>
.asking {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}
.asking__heading {
  margin: 0;
}
.asking__list {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-half);
  margin: 0;
  padding: 0;
  list-style: none;
}
.asking__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}
.asking__who {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.asking__name,
.asking__email {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asking__email {
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
}
/* Wide enough for the longest wording in GRANT_OPTIONS, so the row does not
   change width as a level is chosen. */
.asking__level {
  width: 160px;
}
</style>
