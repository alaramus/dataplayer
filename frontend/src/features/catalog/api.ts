import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { ComputedRef, Ref } from "vue"

import { ConnectorsService } from "@/client"
import type { ActionPreview, ActionResult, NodeSearchResult } from "@/client"
import { jobsKey } from "@/features/activity/api"
import { messageOf, statusOf } from "@/shared/api/errors"
import { problemMessage, t } from "@/shared/i18n"
import { freshnessOf } from "@/shared/freshness/freshness"
import type { Freshness } from "@/shared/freshness/freshness"
import { useOperations } from "@/shared/operations"
import type { OperationHandle } from "@/shared/operations"
import { nodeSetOf, reloadedBy, summarize } from "./actions"
import type { ActionFailure, ActionOutcome } from "./actions"
import type { CatalogNode } from "./nodes"

export const catalogKey = (connectorId: string, nodeId: string | null) =>
  ["catalog", connectorId, nodeId] as const

/**
 * One level, and whether it was read or remembered.
 *
 * The pair is what the cache holds, rather than the nodes with a note about
 * them kept somewhere else: a second store beside vue-query would have its own
 * eviction and would come apart from the level it describes (D105).
 */
export interface CatalogPage {
  nodes: CatalogNode[]
  freshness: Freshness
}

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
  ): Promise<CatalogPage> {
    return queryClient.fetchQuery({
      queryKey: catalogKey(connectorId, nodeId),
      queryFn: async () => {
        const response = await ConnectorsService.readCatalog({
          path: { connector_id: connectorId },
          query: {
            ...(nodeId === null ? {} : { node_id: nodeId }),
            ...(refresh ? { refresh: true } : {}),
          },
        })
        return {
          nodes: response.data,
          freshness: freshnessOf(response.headers as Record<string, unknown>),
        }
      },
      staleTime: 60_000,
    })
  }
}

/**
 * The tables inside one node: the sheets of a workbook.
 *
 * The same query the catalog itself makes, by the same key, so a tab that
 * offers the sheets of a file the catalog has already listed reads nothing
 * again. Only nodes that open as a table are offered — a container of tables
 * holds nothing else today, and a listing that quietly included something
 * unopenable would be a switcher with a dead entry in it.
 */
export function useSiblingTables(
  connectorId: Ref<string>,
  containerId: Ref<string | null>
): ComputedRef<CatalogNode[]> {
  const query = useQuery({
    queryKey: computed(() => catalogKey(connectorId.value, containerId.value)),
    queryFn: async (): Promise<CatalogPage> => {
      const response = await ConnectorsService.readCatalog({
        path: { connector_id: connectorId.value },
        query: { node_id: containerId.value ?? "" },
      })
      return {
        nodes: response.data,
        freshness: freshnessOf(response.headers as Record<string, unknown>),
      }
    },
    enabled: computed(() => containerId.value !== null),
    staleTime: 60_000,
  })
  // Answered rather than handed over, and empty when there is no container to
  // ask about: a disabled query still reads whatever is under its key, and
  // the key of "no container" is the root of the catalog — which is how every
  // table in a connection came to offer the files of its root as sheets.
  return computed(() =>
    containerId.value === null
      ? []
      : (query.data.value?.nodes ?? []).filter((node) =>
          node.representations.some((one) => one.kind === "table")
        )
  )
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

/** Where a search looked: at names, or inside the files themselves (D76). */
export type SearchScope = "names" | "contents"

export const nodeSearchKey = (
  connectorId: string,
  nodeId: string | null,
  query: string,
  scope: SearchScope = "names"
) => ["nodeSearch", connectorId, nodeId, query, scope] as const

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
    query: string,
    scope: SearchScope = "names"
  ): Promise<NodeSearchResult> {
    return queryClient.fetchQuery({
      queryKey: nodeSearchKey(connectorId, nodeId, query, scope),
      queryFn: async () => {
        const request = {
          path: { connector_id: connectorId },
          query: nodeId === null ? { query } : { node_id: nodeId, query },
        }
        // Two routes, because they are two promises: one matches a name and
        // the other opens every file it is allowed to, and a source that can
        // do the first without the second answers 501 to it (D76).
        return scope === "contents"
          ? (await ConnectorsService.searchCatalogContents(request)).data
          : (await ConnectorsService.searchCatalog(request)).data
      },
      staleTime: 60_000,
    })
  }
}

export const actionsKey = (connectorId: string, nodeIds: string[] | null) =>
  ["actions", connectorId, nodeIds] as const

/**
 * Everything this source can do, and which of it these nodes admit. Asked of
 * the server: whether a node may be renamed depends on its state as well as
 * its kind, and whether an action applies to many at once only the action
 * knows. No actions at all answers 501, which is settled rather than a failure
 * to retry.
 *
 * `enabled` is for the question with no subject yet: nothing is ticked, and
 * asking about the root would answer a different question.
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
  label?: string
  /** The nodes to act on. One filled form, applied to each in turn. */
  nodeIds: (string | null)[]
  params: Record<string, unknown>
  reviewedFingerprint?: string
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
  file: File | null,
  operation: OperationHandle
): Promise<ActionResult> {
  const path = { connector_id: input.connectorId, action_name: input.name }
  if (file) {
    return (
      await ConnectorsService.runActionWithFile({
        path,
        onUploadProgress: (event) => operation.transfer(event.loaded, event.total),
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
      body: {
        node_id: nodeId,
        params: input.params,
        ...(input.reviewedFingerprint === undefined
          ? {} : { reviewed_fingerprint: input.reviewedFingerprint }),
      },
    })
  ).data
}

/**
 * Performing an action over everything that was ticked. Two transports, one
 * mutation, chosen by whether a file was picked.
 *
 * A set is done one at a time and a refusal does not stop the rest: deleting
 * four of five and saying which survived beats stopping at the first. Files
 * are the same statement on the other axis — one request per node and file.
 */
export function useRunAction() {
  const queryClient = useQueryClient()
  const operations = useOperations()

  return useMutation({
    mutationFn: async (input: ActionInput): Promise<ActionOutcome> => {
      const together = togetherIn(input)
      const carried: (File | null)[] = input.files?.length ? input.files : [null]
      const requests = input.nodeIds.flatMap((nodeId) => carried.map((file) => ({ nodeId, file })))
      const total = together === null ? requests.length : 1
      const label = input.label ?? input.name
      const operation = operations.start(label, total)
      try {
        if (together !== null) {
          // One request, so one answer: a refusal arrives as an exception and
          // is read where a single action's refusal is read.
          await operation.next(t("catalog.actions.waiting"))
          const result = (
            await ConnectorsService.runActionOnSet({
              path: { connector_id: input.connectorId, action_name: input.name },
              body: { node_ids: together, params: input.params },
            })
          ).data
          operation.complete()
          // Carried out as far as it went: what was left is said node by node,
          // in the same report a run node by node gives.
          const failures: ActionFailure[] = (result.refused ?? []).map((refusal) => ({
            nodeId: refusal.node_id,
            message: refusal.problem ? problemMessage(refusal.problem) ?? refusal.message : refusal.message,
          }))
          if (failures.length === 0) {
            operation.finish(result.message)
            return { done: [result], failures: [], total: 1 }
          }
          const outcome: ActionOutcome = {
            done: [result],
            failures,
            total: together.length,
            doneCount: together.length - failures.length,
          }
          operation.finish(summarize(outcome, label), true)
          return outcome
        }
        const done: ActionResult[] = []
        const failures: ActionFailure[] = []
        const skipped: ActionFailure[] = []
        for (const [index, { nodeId, file }] of requests.entries()) {
          if (!(await operation.next(file?.name ?? nodeId ?? t("catalog.actions.waiting")))) {
            skipped.push(...requests.slice(index).map((request) => ({
              nodeId: request.nodeId,
              message: t("catalog.actions.not_started"),
              ...(request.file === null ? {} : { file: request.file }),
            })))
            break
          }
          try {
            const result = await performOne(input, nodeId, file, operation)
            done.push(result)
            // A paused queue may stay open indefinitely. Completed changes
            // must already be visible before the batch's final callback.
            if (total > 1) {
              for (const changed of result.reload_node_ids) {
                void queryClient.invalidateQueries({ queryKey: catalogKey(input.connectorId, changed) })
              }
            }
          } catch (cause) {
            // The first refusal is re-raised when it is the only request: a
            // single action must still show a field error in its own form.
            if (total === 1) throw cause
            failures.push({
              nodeId,
              message: messageOf(cause, t("catalog.actions.could_not_be_done")),
              ...(file === null ? {} : { file }),
              conflict: statusOf(cause) === 409,
            })
          } finally {
            operation.complete()
          }
        }
        const outcome: ActionOutcome = { done, failures, total, ...(skipped.length ? { skipped } : {}) }
        operation.finish(summarize(outcome, label), failures.length > 0)
        return outcome
      } catch (cause) {
        operation.fail(messageOf(cause, t("catalog.actions.failed")))
        throw cause
      }
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
 * Hand a reviewed action to the server as an owned job (D123).
 *
 * No local operation is started: the job is the record of the work, and the
 * activity sheet reads it from the server like any other job (D95).
 */
export function useStartActionJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: {
      connectorId: string
      name: string
      nodeId: string | null
      params: Record<string, unknown>
      reviewedFingerprint: string
    }) =>
      (
        await ConnectorsService.startActionJob({
          path: { connector_id: input.connectorId, action_name: input.name },
          body: {
            node_id: input.nodeId,
            params: input.params,
            reviewed_fingerprint: input.reviewedFingerprint,
          },
        })
      ).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: jobsKey })
    },
  })
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

/** Resolve a selected node into a connector draft; saving is a separate action. */
export function usePrepareConnectorAction() {
  return useMutation({
    mutationFn: async (input: { connectorId: string; name: string; nodeId: string }) =>
      (
        await ConnectorsService.prepareConnectorAction({
          path: { connector_id: input.connectorId, action_name: input.name },
          body: { node_id: input.nodeId, params: {} },
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
/** What the fields of one action's form may be, for one node; asked as the form opens. */
export function useFieldHints(
  connectorId: Ref<string>,
  name: Ref<string | null>,
  nodeId: Ref<string | null | undefined>,
  enabled: Ref<boolean>
) {
  return useQuery({
    queryKey: computed(() => ["action-hints", connectorId.value, name.value, nodeId.value]),
    enabled,
    // Asked again each time the form opens: a column added since is offered.
    staleTime: 0,
    refetchOnWindowFocus: false,
    queryFn: async () =>
      (
        await ConnectorsService.actionFieldHints({
          path: { connector_id: connectorId.value, action_name: name.value ?? "" },
          body: { node_id: nodeId.value ?? null, params: {} },
        })
      ).data,
  })
}

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
