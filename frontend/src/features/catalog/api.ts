import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type { ActionPreview, ActionResult, NodeSearchResult } from "@/client"
import { messageOf, statusOf } from "@/shared/api/errors"
import { nodeSetOf, reloadedBy } from "./actions"
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
    nodeId: string | null,
    refresh = false
  ): Promise<CatalogNode[]> {
    return queryClient.fetchQuery({
      queryKey: catalogKey(connectorId, nodeId),
      queryFn: async () =>
        (
          await ConnectorsService.readCatalog({
            path: { connector_id: connectorId },
            query: {
              ...(nodeId === null ? {} : { node_id: nodeId }),
              ...(refresh ? { refresh: true } : {}),
            },
          })
        ).data,
      staleTime: 60_000,
    })
  }
}

export const nodePathKey = (connectorId: string, nodeId: string) =>
  ["nodePath", connectorId, nodeId] as const

/**
 * Loader for the chain of nodes from the root of a connector down to one node.
 *
 * Through the cache for the reason the catalog loader is: pointing at the same
 * table twice must not ask the source twice. Kept fresh for as long as a
 * level, since the two answer about the same thing.
 */
export function useNodePathLoader() {
  const queryClient = useQueryClient()

  return async function loadPath(
    connectorId: string,
    nodeId: string
  ): Promise<CatalogNode[]> {
    return queryClient.fetchQuery({
      queryKey: nodePathKey(connectorId, nodeId),
      queryFn: async () =>
        (
          await ConnectorsService.readNodePath({
            path: { connector_id: connectorId },
            query: { node_id: nodeId },
          })
        ).data,
      staleTime: 60_000,
    })
  }
}

export const nodeSearchKey = (connectorId: string, nodeId: string | null, query: string) =>
  ["nodeSearch", connectorId, nodeId, query] as const

/**
 * Search below one level, on demand.
 *
 * A loader rather than a query with a reactive key: a search happens when
 * somebody asks for it, not when the text they are typing changes. The answer
 * is still cached, so asking twice for the same words in the same folder costs
 * one walk of the tree (D76).
 */
export function useNodeSearcher() {
  const queryClient = useQueryClient()

  return async function searchNodes(
    connectorId: string,
    nodeId: string | null,
    query: string
  ): Promise<NodeSearchResult> {
    return queryClient.fetchQuery({
      queryKey: nodeSearchKey(connectorId, nodeId, query),
      queryFn: async () =>
        (
          await ConnectorsService.searchCatalog({
            path: { connector_id: connectorId },
            query: nodeId === null ? { query } : { node_id: nodeId, query },
          })
        ).data,
      staleTime: 60_000,
    })
  }
}

export const actionsKey = (connectorId: string, nodeIds: string[] | null) =>
  ["actions", connectorId, nodeIds] as const

/**
 * Everything this source can do, and which of it these nodes admit.
 *
 * Asked of the server rather than worked out here: whether a node may be
 * renamed depends on its state as well as its kind, and what applies to a set
 * is what applies to all of it — including whether an action can be applied to
 * many at once, which only the action knows. A source with no actions at all
 * answers 501, which is a settled answer rather than a failure to retry.
 *
 * `enabled` is for the question that has no subject yet: nothing is ticked, so
 * there is nothing to ask about, and asking about the root instead would
 * answer a different question.
 */
export function useNodeActions(
  connectorId: Ref<string | null>,
  nodeIds: Ref<string[] | null>,
  enabled?: Ref<boolean>
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
    enabled: computed(() => connectorId.value !== null && (enabled?.value ?? true)),
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
  /**
   * The files to carry, one request each.
   *
   * An action that takes a file may be handed several, and the transport is
   * then the same request repeated: a refused name is one file's answer
   * rather than the whole set's, and what did arrive stays arrived.
   */
  files?: File[]
  /**
   * Whether the source takes the whole selection in one request.
   *
   * The action said so, and the client only obeys: an action whose answer is
   * about the set — dropping relations that depend on each other — is refused
   * three times over when it is sent three times.
   */
  asSet?: boolean
}

async function performOne(
  input: ActionInput,
  nodeId: string | null,
  file: File | null
): Promise<ActionResult> {
  const path = { connector_id: input.connectorId, action_name: input.name }
  if (file) {
    return (
      await ConnectorsService.runActionWithFile({
        path,
        body: {
          file,
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
 *
 * A set of files is the same statement about the other axis: one request per
 * node and file, so three files into one folder are three uploads and the
 * second being refused says nothing about the third.
 */
export function useRunAction() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: ActionInput): Promise<ActionOutcome> => {
      const together = togetherIn(input)
      if (together !== null) {
        // One request, so one answer: a refusal arrives as an exception and
        // is read where a single action's refusal is read.
        const result = (
          await ConnectorsService.runActionOnSet({
            path: { connector_id: input.connectorId, action_name: input.name },
            body: { node_ids: together, params: input.params },
          })
        ).data
        return { done: [result], failures: [], total: 1 }
      }
      const done: ActionResult[] = []
      const failures: ActionFailure[] = []
      // An action carrying nothing is one request per node all the same; the
      // loop below is over pairs either way.
      const carried: (File | null)[] =
        input.files !== undefined && input.files.length > 0 ? input.files : [null]
      const total = input.nodeIds.length * carried.length
      for (const nodeId of input.nodeIds) {
        for (const file of carried) {
          try {
            done.push(await performOne(input, nodeId, file))
          } catch (cause) {
            // The first refusal is re-raised when it is the only request: a
            // single action must still show a field error in its own form.
            if (total === 1) throw cause
            failures.push({
              nodeId,
              message: messageOf(cause, "Could not be done"),
              ...(file === null ? {} : { file }),
              conflict: statusOf(cause) === 409,
            })
          }
        }
      }
      return { done, failures, total }
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

/**
 * The selection to send in one request, or nothing when it is sent per node.
 *
 * A file the action carries makes it one request per file whatever else the
 * action says, so that falls back to the repeated transport rather than being
 * a special case inside the other one.
 */
function togetherIn(input: ActionInput): string[] | null {
  if (input.asSet !== true) return null
  if (input.files !== undefined && input.files.length > 0) return null
  return nodeSetOf(input.nodeIds)
}

/**
 * Ask one source-declared action to download its whole selected target set.
 *
 * With the filled form, because a download may be a choice as well as a
 * selection — which dialect to write a model in — and the source validates it
 * exactly as it validates the parameters of anything else (D73).
 */
export function useDownloadAction() {
  return useMutation({
    mutationFn: async (input: {
      connectorId: string
      name: string
      nodeIds: string[]
      params?: Record<string, unknown>
    }) =>
      (
        await ConnectorsService.prepareActionDownload({
          path: { connector_id: input.connectorId, action_name: input.name },
          body: { node_ids: input.nodeIds, params: input.params ?? {} },
        })
      ).data,
  })
}

/**
 * Ask one action what it would do, without doing it.
 *
 * A mutation although it changes nothing, for the reason following a
 * reference is one: it is asked as a form is filled in, its answer is shown
 * once beside that form and never read again, so there is nothing for a cache
 * key to be about.
 */
export function usePreviewAction() {
  return useMutation({
    mutationFn: async (input: {
      connectorId: string
      name: string
      nodeId: string | null
      params: Record<string, unknown>
    }): Promise<ActionPreview> =>
      (
        await ConnectorsService.previewAction({
          path: { connector_id: input.connectorId, action_name: input.name },
          body: { node_id: input.nodeId, params: input.params },
        })
      ).data,
  })
}

/**
 * Ask what one action would do to a whole selection.
 *
 * A separate mutation rather than a flag on the one above: the two are
 * different requests, and an answer about a set is one account rather than
 * several stitched together here.
 */
export function usePreviewActionOnSet() {
  return useMutation({
    mutationFn: async (input: {
      connectorId: string
      name: string
      nodeIds: string[]
      params: Record<string, unknown>
    }): Promise<ActionPreview> =>
      (
        await ConnectorsService.previewActionOnSet({
          path: { connector_id: input.connectorId, action_name: input.name },
          body: { node_ids: input.nodeIds, params: input.params },
        })
      ).data,
  })
}
