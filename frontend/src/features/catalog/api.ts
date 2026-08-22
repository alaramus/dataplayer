import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type { ActionResult, FetchRequest } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { reloadedBy } from "./actions"
import type { ActionFailure, ActionOutcome } from "./actions"
import type { CatalogNode } from "./nodes"

export const catalogKey = (connectorId: string, nodeId: string | null) =>
  ["catalog", connectorId, nodeId] as const

/**
 * Loader for QTree, whose lazy loading is callback-driven.
 *
 * Goes through queryClient.fetchQuery rather than calling the service
 * directly, so expanded branches still land in the vue-query cache and
 * re-expanding a node does not hit the source again.
 */
export function useCatalogLoader() {
  const queryClient = useQueryClient()

  return async function loadChildren(
    connectorId: string,
    nodeId: string | null
  ): Promise<CatalogNode[]> {
    return queryClient.fetchQuery({
      queryKey: catalogKey(connectorId, nodeId),
      queryFn: async () =>
        (
          await ConnectorsService.readCatalog({
            path: { connector_id: connectorId },
            query: nodeId === null ? {} : { node_id: nodeId },
          })
        ).data,
      staleTime: 60_000,
    })
  }
}

/**
 * Reading a page of rows.
 *
 * A mutation rather than a query: the request is a POST with a structured
 * body, and pages are asked for in response to user action rather than cached
 * by key. The result is short-lived — the grid holds the page it is showing.
 */
export function useFetchRows() {
  return useMutation({
    mutationFn: async (payload: { connectorId: string; request: FetchRequest }) =>
      (
        await ConnectorsService.fetchRows({
          path: { connector_id: payload.connectorId },
          body: payload.request,
        })
      ).data,
  })
}

export const actionsKey = (connectorId: string, nodeIds: string[] | null) =>
  ["actions", connectorId, nodeIds] as const

/**
 * What every one of these nodes can be asked to do.
 *
 * Asked of the server rather than worked out here: whether a node may be
 * renamed depends on its state as well as its kind, and what applies to a set
 * is what applies to all of it — including whether an action can be applied to
 * many at once, which only the action knows. A source with no actions at all
 * answers 501, which is a settled answer rather than a failure to retry.
 */
export function useNodeActions(
  connectorId: Ref<string | null>,
  nodeIds: Ref<string[] | null>
) {
  return useQuery({
    queryKey: computed(() => actionsKey(connectorId.value ?? "", nodeIds.value)),
    queryFn: async () =>
      (
        await ConnectorsService.readActions({
          path: { connector_id: connectorId.value as string },
          body: { node_ids: nodeIds.value },
        })
      ).data,
    enabled: computed(() => connectorId.value !== null),
    retry: false,
    staleTime: 60_000,
  })
}

export interface ActionInput {
  connectorId: string
  name: string
  /** The nodes to act on. One filled form, applied to each in turn. */
  nodeIds: (string | null)[]
  params: Record<string, unknown>
  file?: File | null
}

async function performOne(
  input: ActionInput,
  nodeId: string | null
): Promise<ActionResult> {
  const path = { connector_id: input.connectorId, action_name: input.name }
  if (input.file) {
    return (
      await ConnectorsService.runActionWithFile({
        path,
        body: {
          file: input.file,
          node_id: nodeId ?? "",
          params: JSON.stringify(input.params),
        },
      })
    ).data
  }
  return (
    await ConnectorsService.runAction({
      path,
      body: { node_id: nodeId, params: input.params },
    })
  ).data
}

/**
 * Performing an action over everything that was ticked.
 *
 * Two transports, one mutation: which one is used follows from whether a file
 * was chosen, and the action itself declared that in the listing. A set is
 * done one at a time and a refusal does not stop the rest — deleting four of
 * five files and saying which one survived beats stopping at the first.
 */
export function useRunAction() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: ActionInput): Promise<ActionOutcome> => {
      const done: ActionResult[] = []
      const failures: ActionFailure[] = []
      for (const nodeId of input.nodeIds) {
        try {
          done.push(await performOne(input, nodeId))
        } catch (cause) {
          // The first refusal is re-raised when it is the only node: a single
          // action must still be able to show a field error in its form.
          if (input.nodeIds.length === 1) throw cause
          failures.push({ nodeId, message: messageOf(cause, "Could not be done") })
        }
      }
      return { done, failures, total: input.nodeIds.length }
    },
    onSuccess: async (outcome, input) => {
      // The server says which branch changed; the client does not derive it
      // from the name of the action.
      for (const nodeId of reloadedBy(outcome)) {
        await queryClient.invalidateQueries({
          queryKey: catalogKey(input.connectorId, nodeId),
        })
      }
      await queryClient.invalidateQueries({ queryKey: ["actions", input.connectorId] })
    },
  })
}
