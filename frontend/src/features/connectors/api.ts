import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"

import { AdaptersService, ConnectorsService } from "@/client"
import type { ConnectorCreate, ConnectorUpdate } from "@/client"

export const connectorsKey = ["connectors"] as const
export const adapterTypesKey = ["adapter-types"] as const

export function useConnectors() {
  return useQuery({
    queryKey: connectorsKey,
    queryFn: async () => (await ConnectorsService.readConnectors()).data,
  })
}

export function useAdapterTypes() {
  return useQuery({
    queryKey: adapterTypesKey,
    queryFn: async () => (await AdaptersService.readAdapterTypes()).data,
    // The type registry only changes on deployment, so nothing to refetch.
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useCreateConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: ConnectorCreate) =>
      (await ConnectorsService.createConnector({ body })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: connectorsKey }),
  })
}

export function useUpdateConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { connectorId: string; body: ConnectorUpdate }) =>
      (
        await ConnectorsService.updateConnector({
          path: { connector_id: payload.connectorId },
          body: payload.body,
        })
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: connectorsKey }),
  })
}

export function useDeleteConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (connectorId: string) =>
      (
        await ConnectorsService.deleteConnector({
          path: { connector_id: connectorId },
        })
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: connectorsKey }),
  })
}

export function useCheckConnector() {
  return useMutation({
    mutationFn: async (connectorId: string) =>
      (
        await ConnectorsService.checkConnector({
          path: { connector_id: connectorId },
        })
      ).data,
  })
}

export function useCheckDraft() {
  return useMutation({
    mutationFn: async (body: {
      adapter_type: string
      options: Record<string, unknown>
      connector_id?: string | null
    }) => (await ConnectorsService.checkDraft({ body })).data,
  })
}
