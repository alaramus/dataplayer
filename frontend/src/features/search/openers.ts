import { useRouter } from "vue-router"

import type { Hit, RecentTarget } from "@/client"
import { openQuickChat } from "@/features/ai/quickChatLauncher"
import { requestAiConversation, requestAiProject } from "@/features/ai/state"
import { setDashboardIntent } from "@/features/dashboards/intent"
import { useOpenGuide } from "@/features/guide/windows"
import { setPipelineIntent } from "@/features/pipelines/intent"
import type { PreferenceSectionId } from "@/features/preferences/sections"
import { pointAtService } from "@/features/services/pointed"
import { useBottomPanel } from "@/features/workspace/useBottomPanel"
import { useWorkspaceActions } from "@/features/workspace/state"
import type { OpenHow } from "@/features/workspace/state"
import { useCurrentUser } from "@/shared/auth/currentUser"
import { t } from "@/shared/i18n"
import { forgetOpened, forgetOpenedHit, readOpened, rememberOpened } from "@/shared/search/opened"
import { useToast } from "@/shared/ui"
import { useSpaceStore } from "@/stores/space"

import { openHit, showInCatalog } from "./intents"
import type { Openers } from "./intents"
import { objectLabel } from "./kinds"

/**
 * What the registry's entries call on this screen: the workspace's own ways
 * in. A space is asked for its object before it is shown, so a space shown for
 * the first time by this very press finds the request waiting as it mounts.
 */
export function useHitOpeners(): Openers {
  const actions = useWorkspaceActions()
  const openGuide = useOpenGuide()
  const bottom = useBottomPanel()
  const toast = useToast()
  const router = useRouter()
  const space = useSpaceStore()
  return {
    intent: (intent, how) => actions.openIntent(intent, how),
    connectionWindow: (connectorId) => {
      actions.editConnector(connectorId)
    },
    guidePage: openGuide,
    sourceType: (adapterType) => {
      actions.newConnection(adapterType)
    },
    savedQuery: (documentId, title, how) => {
      actions.openWith(how, () => {
        actions.openQueryDocument({ documentId, title, connectorName: null })
      })
    },
    pipeline: (pipelineId) => {
      setPipelineIntent(pipelineId)
      space.show("pipelines")
    },
    dashboard: (dashboardId) => {
      setDashboardIntent(dashboardId)
      space.show("dashboards")
    },
    conversation: (conversationId) => {
      requestAiConversation(conversationId)
      space.show("ai")
    },
    quickChat: (chatId) => {
      openQuickChat({ kind: "chat", id: chatId })
    },
    project: (projectId) => {
      requestAiProject(projectId)
      space.show("ai")
    },
    service: (serviceId) => {
      pointAtService(serviceId)
      bottom.show("services")
    },
    sshKey: (keyId) => {
      void router.push({
        name: "preferences",
        params: { section: "ssh-keys" satisfies PreferenceSectionId },
        query: { key: keyId },
      })
    },
    tab: (panelId) => {
      actions.openTab(panelId)
    },
    tabGroup: (groupId) => {
      actions.openTabGroup(groupId)
    },
    unopenable: (hit: Hit) => {
      const what = hit.target.kind === "object" ? objectLabel(hit.target.object_type) : hit.title
      toast.info(t("search.unopenable", { what }))
    },
  }
}

/** What a hit offers from the search: opened, or shown in its catalog. */
export interface HitActions {
  open: (hit: Hit) => void | Promise<void>
  showInCatalog: (hit: Hit) => void | Promise<void>
}

/**
 * A hit opened from the search: over the space being shown when that is not
 * Data, as what the agent opens floats (D205), and beside `besidePanel` when
 * there is one to keep in sight.
 */
export function useHitActions(besidePanel?: () => string | null): HitActions {
  const openers = useHitOpeners()
  const space = useSpaceStore()
  const me = useCurrentUser()
  function how(): OpenHow {
    const beside = besidePanel?.() ?? null
    return { float: space.current !== "data", ...(beside === null ? {} : { beside }) }
  }
  // Kept before it opens: an opener that fails still leaves it findable (S6).
  function opened(hit: Hit) {
    rememberOpened(me.data.value?.id, hit)
  }
  return {
    open: (hit) => {
      opened(hit)
      return openHit(hit, openers, how())
    },
    showInCatalog: (hit) => {
      opened(hit)
      return showInCatalog(hit, openers, how())
    },
  }
}

/** What was opened from the search lately, sent with every request as a hint (S6). */
export function useRecentlyOpened(): () => RecentTarget[] {
  const me = useCurrentUser()
  return () => readOpened(me.data.value?.id)
}

/** Taking what was opened lately out of the list: one row, or all of them (D205). */
export function useForgetOpened(): { one: (hit: Hit) => void; all: () => void } {
  const me = useCurrentUser()
  return {
    one: (hit) => forgetOpenedHit(me.data.value?.id, hit),
    all: () => forgetOpened(me.data.value?.id),
  }
}
