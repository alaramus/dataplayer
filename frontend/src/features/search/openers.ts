import { useRouter } from "vue-router"

import type { Hit } from "@/client"
import { openQuickChat } from "@/features/ai/quickChatLauncher"
import { requestAiConversation, requestAiProject } from "@/features/ai/state"
import { setDashboardIntent } from "@/features/dashboards/intent"
import { useOpenGuide } from "@/features/guide/windows"
import { setPipelineIntent } from "@/features/pipelines/intent"
import { pointAtService } from "@/features/services/pointed"
import { useBottomPanel } from "@/features/workspace/useBottomPanel"
import { useWorkspaceActions } from "@/features/workspace/state"
import type { OpenHow } from "@/features/workspace/state"
import { useToast } from "@/shared/ui"
import { useSpaceStore } from "@/stores/space"

import { openHit, showInCatalog } from "./intents"
import type { Openers } from "./intents"
import { OBJECT_LABELS } from "./kinds"

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
      void router.push({ name: "preferences", query: { key: keyId } })
    },
    tab: (panelId) => {
      actions.openTab(panelId)
    },
    tabGroup: (groupId) => {
      actions.openTabGroup(groupId)
    },
    unopenable: (hit: Hit) => {
      const what = hit.target.kind === "object" ? OBJECT_LABELS[hit.target.object_type] : hit.title
      toast.info(`${what} can't be opened from here`)
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
  function how(): OpenHow {
    const beside = besidePanel?.() ?? null
    return { float: space.current !== "data", ...(beside === null ? {} : { beside }) }
  }
  return {
    open: (hit) => openHit(hit, openers, how()),
    showInCatalog: (hit) => showInCatalog(hit, openers, how()),
  }
}
