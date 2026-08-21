import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type { ActionResult, FetchRequest } from "@/client"
import type { CatalogNode } from "./treeNodes"

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

export const actionsKey = (connectorId: string, nodeId: string | null) =>
  ["actions", connectorId, nodeId] as const

/**
 * What the selected node can be asked to do.
 *
 * Asked per node rather than per source type: whether a node may be renamed
 * depends on its state as well as its kind, and the server is the one that
 * knows. A source with no actions at all answers 501, which is a settled
 * answer rather than a failure to retry.
 */
export function useNodeActions(
  connectorId: Ref<string | null>,
  nodeId: Ref<string | null>
) {
  return useQuery({
    queryKey: computed(() => actionsKey(connectorId.value ?? "", nodeId.value)),
    queryFn: async () =>
      (
        await ConnectorsService.readActions({
          path: { connector_id: connectorId.value as string },
          query: nodeId.value === null ? {} : { node_id: nodeId.value },
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
  nodeId: string | null
  params: Record<string, unknown>
  file?: File | null
}

/**
 * Performing an action.
 *
 * Two transports, one mutation: which one is used follows from whether a file
 * was chosen, and the action itself declared that in the listing.
 */
export function useRunAction() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: ActionInput): Promise<ActionResult> => {
      const path = { connector_id: input.connectorId, action_name: input.name }
      if (input.file) {
        return (
          await ConnectorsService.runActionWithFile({
            path,
            body: {
              file: input.file,
              node_id: input.nodeId ?? "",
              params: JSON.stringify(input.params),
            },
          })
        ).data
      }
      return (
        await ConnectorsService.runAction({
          path,
          body: { node_id: input.nodeId, params: input.params },
        })
      ).data
    },
    onSuccess: async (result, input) => {
      // The server says which branch changed; the client does not derive it
      // from the name of the action.
      await queryClient.invalidateQueries({
        queryKey: catalogKey(input.connectorId, result.reload_node_id ?? null),
      })
      await queryClient.invalidateQueries({ queryKey: ["actions", input.connectorId] })
    },
  })
}
