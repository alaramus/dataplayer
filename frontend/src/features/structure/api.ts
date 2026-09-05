import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type {
  AddColumnRequest,
  ColumnDefaultRequest,
  ColumnNullabilityRequest,
  ColumnTypeRequest,
  CreateConstraintRequest,
  CreateIndexRequest,
  DropColumnRequest,
  DropConstraintRequest,
  DropIndexRequest,
  RenameColumnRequest,
} from "@/client"

export const relationModelKey = (connectorId: string, nodeId: string) =>
  ["relationModel", connectorId, nodeId] as const

export const structureInvalidationKeys = (connectorId: string, nodeId: string) =>
  [
    relationModelKey(connectorId, nodeId),
    ["rows", connectorId] as const,
    ["content", connectorId] as const,
  ] as const

export function useRelationModel(
  connectorId: Ref<string>,
  nodeId: Ref<string>,
  /**
   * Whether to ask at all. A structure panel is only ever opened on a node
   * that says it can be described; a row view is opened on any node at all,
   * and asking a source to describe a CSV is asking for a 501.
   */
  enabled?: Ref<boolean>
) {
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
    enabled: computed(() => enabled?.value ?? true),
  })
}

/**
 * One column command, with both stale projections dropped after it.
 *
 * `changed` exists because not every answer is a change: a source may report
 * that the data stands in the way and leave the relation exactly as it was,
 * and re-reading it then costs a round trip to learn nothing.
 */
function useStructureMutation<TBody, TResult>(
  connectorId: Ref<string>,
  nodeId: Ref<string>,
  run: (connectorId: string, body: TBody) => Promise<TResult>,
  changed: (result: TResult) => boolean = () => true
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TBody) => run(connectorId.value, body),
    onSuccess: async (result: TResult) => {
      if (!changed(result)) return
      await Promise.all(
        structureInvalidationKeys(connectorId.value, nodeId.value).map((queryKey) =>
          queryClient.invalidateQueries({ queryKey })
        )
      )
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

export function useColumnNullability(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useStructureMutation(
    connectorId,
    nodeId,
    async (id, body: ColumnNullabilityRequest) =>
      (
        await ConnectorsService.changeColumnNullability({
          path: { connector_id: id },
          body,
        })
      ).data,
    (result) => result.kind === "changed"
  )
}

export function useColumnType(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useStructureMutation(
    connectorId,
    nodeId,
    async (id, body: ColumnTypeRequest) =>
      (
        await ConnectorsService.changeColumnType({ path: { connector_id: id }, body })
      ).data,
    (result) => result.kind === "changed"
  )
}

export function useCreateIndex(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useStructureMutation(
    connectorId,
    nodeId,
    async (id, body: CreateIndexRequest) =>
      (
        await ConnectorsService.createIndex({ path: { connector_id: id }, body })
      ).data,
    (result) => result.kind === "created"
  )
}

export function useDropIndex(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useStructureMutation(connectorId, nodeId, async (id, body: DropIndexRequest) =>
    (
      await ConnectorsService.dropIndex({ path: { connector_id: id }, body })
    ).data
  )
}

export function useCreateConstraint(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useStructureMutation(
    connectorId,
    nodeId,
    async (id, body: CreateConstraintRequest) =>
      (
        await ConnectorsService.createConstraint({ path: { connector_id: id }, body })
      ).data,
    (result) => result.kind === "created"
  )
}

export function useDropConstraint(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useStructureMutation(
    connectorId,
    nodeId,
    async (id, body: DropConstraintRequest) =>
      (
        await ConnectorsService.dropConstraint({ path: { connector_id: id }, body })
      ).data
  )
}

/**
 * The tables a foreign key from this relation could point at.
 *
 * Found by asking the source where this relation lives and what else lives
 * there — never by taking its id apart (D21). Only tables: a view has nothing
 * to be pointed at.
 */
export function useSiblingTables(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => ["siblingTables", connectorId.value, nodeId.value] as const),
    queryFn: async () => {
      const path = (
        await ConnectorsService.readNodePath({
          path: { connector_id: connectorId.value },
          query: { node_id: nodeId.value },
        })
      ).data
      const parent = path.at(-2)
      if (parent === undefined) return []
      const children = (
        await ConnectorsService.readCatalog({
          path: { connector_id: connectorId.value },
          query: { node_id: parent.id },
        })
      ).data
      return children.filter((node) => node.kind === "table")
    },
    staleTime: 60_000,
  })
}

/** What the chosen target says it can be pointed at by. */
export function useCandidateKeys(connectorId: Ref<string>, targetNodeId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => relationModelKey(connectorId.value, targetNodeId.value)),
    queryFn: async () =>
      (
        await ConnectorsService.readRelationModel({
          path: { connector_id: connectorId.value },
          query: { node_id: targetNodeId.value },
        })
      ).data,
    enabled: computed(() => targetNodeId.value !== ""),
    staleTime: 5 * 60_000,
  })
}
