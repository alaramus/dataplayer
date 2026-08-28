import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type {
  AddColumnRequest,
  ColumnDefaultRequest,
  DropColumnRequest,
  RenameColumnRequest,
} from "@/client"

export const relationModelKey = (connectorId: string, nodeId: string) =>
  ["relationModel", connectorId, nodeId] as const

export function useRelationModel(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => relationModelKey(connectorId.value, nodeId.value)),
    queryFn: async () =>
      (
        await ConnectorsService.readRelationModel({
          path: { connector_id: connectorId.value },
          query: { node_id: nodeId.value },
        })
      ).data,
    staleTime: 5 * 60_000,
  })
}

function useStructureMutation<TBody>(
  connectorId: Ref<string>,
  nodeId: Ref<string>,
  run: (connectorId: string, body: TBody) => Promise<unknown>
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TBody) => run(connectorId.value, body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: relationModelKey(connectorId.value, nodeId.value),
        }),
        queryClient.invalidateQueries({ queryKey: ["rows", connectorId.value] }),
      ])
    },
  })
}

export function useAddColumn(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useStructureMutation(connectorId, nodeId, async (id, body: AddColumnRequest) =>
    (
      await ConnectorsService.addColumn({ path: { connector_id: id }, body })
    ).data
  )
}

export function useDropColumn(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useStructureMutation(connectorId, nodeId, async (id, body: DropColumnRequest) =>
    (
      await ConnectorsService.dropColumn({ path: { connector_id: id }, body })
    ).data
  )
}

export function useRenameColumn(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useStructureMutation(connectorId, nodeId, async (id, body: RenameColumnRequest) =>
    (
      await ConnectorsService.renameColumn({ path: { connector_id: id }, body })
    ).data
  )
}

export function useColumnDefault(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useStructureMutation(connectorId, nodeId, async (id, body: ColumnDefaultRequest) =>
    (
      await ConnectorsService.changeColumnDefault({ path: { connector_id: id }, body })
    ).data
  )
}
