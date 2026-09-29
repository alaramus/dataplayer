<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { ConnectorsService, SharesService } from "@/client"
import { useNodePathLoader } from "@/features/catalog/api"
import { useRequestAccess } from "@/features/shares/api"
import { setShareIntent } from "@/features/shares/intent"
import { useAccessRequestEvents, wordingOf } from "@/features/shares/requests"
import { messageOf, statusOf } from "@/shared/api/errors"
import { AppButton, AppCard, AppSection, AppSpinner, useToast } from "@/shared/ui"

/**
 * Where a shared link lands.
 *
 * The asking happens here rather than in the workspace because this is the
 * screen that has to explain the answers: no standing on the connection, a
 * node that is gone, a connection switched off. What it cannot do is open a
 * tab, so a link that resolves is left for the workspace and this screen steps
 * out of the way. See D60.
 */
type Landing =
  | { kind: "loading" }
  | {
      kind: "barred"
      sharedBy: string
      connector: string
      node: string
      requested: boolean
    }
  | { kind: "missing" }
  | { kind: "old" }
  | { kind: "gone"; connector: string; node: string }
  | { kind: "disabled"; connector: string }
  | { kind: "failed"; message: string }

const route = useRoute()
const router = useRouter()
const toast = useToast()
const loadPath = useNodePathLoader()
const requestAccess = useRequestAccess()
const landing = ref<Landing>({ kind: "loading" })

function toWorkspace() {
  void router.push({ name: "workspace" })
}

/**
 * Ask the owner for the connection this link is on.
 *
 * The ask is durable, so nothing is lost if they are not here to hear it; what
 * this screen then shows is that it is waiting, rather than the button again.
 * See D61.
 */
async function ask() {
  const token = route.params.token
  const waiting = landing.value
  if (typeof token !== "string" || waiting.kind !== "barred") return
  try {
    await requestAccess.mutateAsync(token)
    landing.value = { ...waiting, requested: true }
  } catch (error) {
    toast.error(messageOf(error, "That request could not be sent"))
  }
}

async function resolve() {
  const token = route.params.token
  if (typeof token !== "string") {
    landing.value = { kind: "missing" }
    return
  }

  let resolved
  try {
    resolved = (await SharesService.resolveShare({ path: { token } })).data
  } catch (error) {
    const status = statusOf(error)
    // A token that never existed and one that was deleted answer alike, so
    // this screen cannot tell them apart either.
    landing.value =
      status === 404
        ? { kind: "missing" }
        : status === 409
          ? { kind: "old" }
          : { kind: "failed", message: "This link could not be opened" }
    return
  }

  if (resolved.state === "no_access") {
    landing.value = {
      kind: "barred",
      sharedBy: resolved.shared_by,
      connector: resolved.connector_label,
      node: resolved.node_label,
      requested: resolved.requested === true,
    }
    return
  }

  try {
    const connector = (
      await ConnectorsService.readConnector({
        path: { connector_id: resolved.connector_id },
      })
    ).data
    if (!connector.enabled) {
      landing.value = { kind: "disabled", connector: connector.name }
      return
    }
    // The catalog is asked where the node lives, which is also how the node's
    // own properties are learnt — and how a node that has since been dropped
    // becomes an explanation rather than a broken tab.
    const path = await loadPath(connector.id, resolved.node_id)
    const node = path.at(-1)
    if (node === undefined) {
      landing.value = {
        kind: "gone",
        connector: connector.name,
        node: resolved.node_label,
      }
      return
    }
    setShareIntent({
      connector,
      nodeId: node.id,
      title: node.name,
      describable: node.describable === true,
      representations: node.representations,
      view: resolved.view,
      sharedBy: resolved.shared_by,
    })
    await router.replace({ name: "workspace" })
  } catch (error) {
    landing.value =
      statusOf(error) === 409
        ? { kind: "disabled", connector: resolved.connector_label }
        : { kind: "gone", connector: resolved.connector_label, node: resolved.node_label }
  }
}

onMounted(resolve)

/**
 * An answer, while the person is sitting here waiting for one.
 *
 * The link is asked again rather than patched from the event: the answer is a
 * grant, and whether this link opens is the server's to say. Somebody waiting
 * on this screen and nothing else is the one case where arriving at the view
 * unasked is what they wanted — everywhere else nothing opens by itself.
 */
const answered = ref("")

useAccessRequestEvents({
  onAsked: () => {},
  onAnswered: (event) => {
    answered.value = wordingOf(event)
    void resolve()
  },
})
</script>

<template>
  <div class="share-landing-page">
    <AppCard
      size="sm"
      title="Shared view"
      data-testid="share-landing"
    >
      <AppSection>
        <AppSpinner v-if="landing.kind === 'loading'" />

        <template v-else-if="landing.kind === 'barred'">
          <p data-testid="share-no-access">
            {{ landing.sharedBy }} shared <strong>{{ landing.node }}</strong> from the
            connection <strong>{{ landing.connector }}</strong>. You have no access to it yet.
          </p>
          <p
            v-if="answered"
            data-testid="share-answered"
          >
            {{ answered }}
          </p>
          <p
            v-else-if="landing.requested"
            data-testid="share-requested"
          >
            The owner of {{ landing.connector }} has been asked. You will be told
            when they answer.
          </p>
        </template>

        <p
          v-else-if="landing.kind === 'missing'"
          data-testid="share-missing"
        >
          This link does not exist, or it was deleted.
        </p>

        <p
          v-else-if="landing.kind === 'old'"
          data-testid="share-old"
        >
          This link was made by an earlier version of the application and can no
          longer be opened.
        </p>

        <p
          v-else-if="landing.kind === 'gone'"
          data-testid="share-gone"
        >
          <strong>{{ landing.node }}</strong> is no longer in
          <strong>{{ landing.connector }}</strong>. Open the connection to see what is there now.
        </p>

        <p
          v-else-if="landing.kind === 'disabled'"
          data-testid="share-disabled"
        >
          <strong>{{ landing.connector }}</strong> is switched off, so nothing can be
          read from it.
        </p>

        <p
          v-else
          data-testid="share-failed"
        >
          {{ landing.message }}
        </p>
      </AppSection>

      <AppSection v-if="landing.kind !== 'loading'">
        <AppButton
          v-if="landing.kind === 'barred' && !landing.requested"
          label="Request access"
          data-testid="share-request"
          :loading="requestAccess.isPending.value"
          @click="ask"
        />
        <AppButton
          variant="quiet"
          label="Go to the workspace"
          data-testid="share-to-workspace"
          @click="toWorkspace"
        />
      </AppSection>
    </AppCard>
  </div>
</template>

<style scoped>
.share-landing-page { min-height: 100vh; display: grid; place-items: center; padding: var(--dp-space-4); background: var(--dp-chrome-raised); }
</style>
