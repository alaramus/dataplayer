import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"

import { AdaptersService, ConnectorsService } from "@/client"
import type { ConnectorCreate, ConnectorsPublic, ConnectorUpdate } from "@/client"

export const connectorsKey = ["connectors"] as const
export const adapterTypesKey = ["adapter-types"] as const

export function useConnectors() {
  return useQuery({
    queryKey: connectorsKey,
    queryFn: async () => (await ConnectorsService.readConnectors()).data,
  })
}

/**
 * What a connection is called now.
 *
 * By id and out of the list, never from a name copied when a tab was opened.
 * A rename leaves every such copy behind, and the name is the word a console
 * has to type back to leave read-only — the server compares it with the one
 * the connection has now (D66).
 */
export function connectorNameOf(
  connectors: ConnectorsPublic | undefined,
  connectorId: string | null
): string | null {
  if (connectorId === null) return null
  return connectors?.data.find((one) => one.id === connectorId)?.name ?? null
}

/**
 * The colour chosen for a connection, if one was.
 *
 * Beside the name and for the same reason: read by id out of the list, never
 * copied onto whatever is drawn in it. A colour saved or reset while a
 * catalog is open has to reach that catalog, and a copy taken when the panel
 * opened would not.
 */
export function connectorColorOf(
  connectors: ConnectorsPublic | undefined,
  connectorId: string | null
): string | null {
  if (connectorId === null) return null
  return connectors?.data.find((one) => one.id === connectorId)?.tab_color ?? null
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

export function useCheckDraft() {
  return useMutation({
    mutationFn: async (body: {
      adapter_type: string
      options: Record<string, unknown>
      connector_id?: string | null
    }) => (await ConnectorsService.checkDraft({ body })).data,
  })
}

/**
 * The connection string of a draft, composed by the server.
 *
 * A request while the form is being typed into, and that is the price of the
 * rule living in one place: the driver knows how its own address is built,
 * and a template filled in on the client would be the same statement made
 * twice. It opens no connection, so the cost is the round trip and nothing
 * more. A source that has no such address answers 501. See the spec, O8.
 */
export function useDescribeDraft() {
  return useMutation({
    mutationFn: async (body: {
      adapter_type: string
      options: Record<string, unknown>
      connector_id?: string | null
    }) => (await ConnectorsService.describeDraft({ body })).data,
  })
}

/**
 * A pasted connection string, taken apart into form values.
 *
 * Asked of the server for the same reason the string is composed there: the
 * rule for reading a DSN belongs to the driver. The driver also names the way
 * of connecting — a form deciding that from the presence of a password would
 * be a rule about authentication in a component that knows none.
 *
 * Nothing is opened, and nothing is stored. See the spec, V5 and V7.
 */
export function useParseUrl() {
  return useMutation({
    mutationFn: async (body: { adapter_type: string; url: string }) =>
      (await ConnectorsService.parseUrl({ body })).data,
  })
}
