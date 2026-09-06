import { useMutation, useQuery } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type { TableDefinition, TablePlan } from "@/client"

export const optionsKey = (connectorId: string, nodeId: string) =>
  ["tableDesign", connectorId, nodeId] as const

/**
 * What the destination will accept a table with, asked once per window.
 *
 * Types, index methods, functions, operator classes and collations all come
 * from the connected server; nothing here keeps a list of its own, because
 * which of them exist depends on the version and on what is installed (D117).
 */
export function useTableDesignOptions(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => optionsKey(connectorId.value, nodeId.value)),
    queryFn: async () => {
      const response = await ConnectorsService.tableDesignOptions({
        path: { connector_id: connectorId.value },
        body: { node_id: nodeId.value },
      })
      return response.data
    },
    enabled: computed(() => connectorId.value !== "" && nodeId.value !== ""),
    staleTime: 300_000,
    retry: false,
  })
}

export interface PlanRequest {
  connectorId: string
  nodeId: string
  definition: TableDefinition
  /** Which draft this is about, echoed back so a late answer can be dropped. */
  revision: number
}

/**
 * The statements a definition would become.
 *
 * A mutation rather than a query although it changes nothing: it is asked
 * again on every pause in the typing, and caching answers by definition would
 * keep every intermediate draft alive for the life of the window.
 */
export function usePlanTable() {
  return useMutation({
    mutationFn: async (request: PlanRequest): Promise<TablePlan> => {
      const response = await ConnectorsService.planTable({
        path: { connector_id: request.connectorId },
        body: {
          node_id: request.nodeId,
          definition: request.definition,
          revision: request.revision,
        },
      })
      return response.data
    },
  })
}

export const schemasKey = (connectorId: string) =>
  ["tableDesign", "schemas", connectorId] as const

/** The groupings of this connection a foreign key may point into. */
export function useDatabaseSchemas(connectorId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => schemasKey(connectorId.value)),
    queryFn: async () => {
      const response = await ConnectorsService.readCatalog({
        path: { connector_id: connectorId.value },
        query: {},
      })
      return response.data.filter(
        (node) => node.kind === "schema" && node.is_system !== true
      )
    },
    enabled: computed(() => connectorId.value !== ""),
    staleTime: 60_000,
  })
}

export const candidateKeysKey = (connectorId: string, nodeId: string) =>
  ["tableDesign", "keys", connectorId, nodeId] as const

/**
 * What one relation says may be pointed at, and what it calls its columns.
 *
 * Read from the target rather than guessed: a column called `id` is not
 * evidence of a key, and which constraints can be referenced is the source's
 * rule (D22).
 */
export function useCandidateKeys(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => candidateKeysKey(connectorId.value, nodeId.value)),
    queryFn: async () => {
      const response = await ConnectorsService.readRelationModel({
        path: { connector_id: connectorId.value },
        query: { node_id: nodeId.value },
      })
      return response.data.candidate_keys ?? []
    },
    enabled: computed(() => connectorId.value !== "" && nodeId.value !== ""),
    staleTime: 60_000,
    retry: false,
  })
}
