import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { DeclaredReferencesService } from "@/client"
import type { DeclaredReferenceCreate } from "@/client"

/**
 * The references one person has drawn, and the drawing and removing of them.
 *
 * Server state, so vue-query and not a store (D6). Keyed by the node they are
 * listed for, because that is what a structure panel is open about; drawing or
 * removing one drops every list, since the other end's list changed too.
 */

export const declaredReferencesKey = (connectorId: string, nodeId: string) =>
  ["declaredReferences", connectorId, nodeId] as const

export function useDeclaredReferences(
  connectorId: MaybeRefOrGetter<string>,
  nodeId: MaybeRefOrGetter<string>
) {
  const connector = computed(() => toValue(connectorId))
  const node = computed(() => toValue(nodeId))
  return useQuery({
    queryKey: computed(() => declaredReferencesKey(connector.value, node.value)),
    queryFn: async () =>
      (
        await DeclaredReferencesService.referencesListDeclaredReferences({
          query: { connector_id: connector.value, node_id: node.value },
        })
      ).data,
  })
}

/**
 * Drop what a drawn reference changes: every list of them, and the pages of
 * both connections, because the arrow is part of a page (D106).
 */
function useReferenceChange<TInput>(
  run: (input: TInput) => Promise<unknown>,
  touched: (input: TInput) => string[]
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSuccess: async (_result, input: TInput) => {
      await queryClient.invalidateQueries({ queryKey: ["declaredReferences"] })
      for (const connectorId of new Set(touched(input))) {
        await queryClient.invalidateQueries({ queryKey: ["rows", connectorId] })
      }
    },
  })
}

export function useDeclareReference() {
  return useReferenceChange(
    async (body: DeclaredReferenceCreate) =>
      (await DeclaredReferencesService.referencesDeclareReference({ body })).data,
    (body) => body.ends.map((end) => end.connector_id)
  )
}

export function useUndeclareReference() {
  return useReferenceChange(
    async (input: { referenceId: string; connectorIds: string[] }) =>
      (
        await DeclaredReferencesService.referencesUndeclareReference({
          path: { reference_id: input.referenceId },
        })
      ).data,
    (input) => input.connectorIds
  )
}
