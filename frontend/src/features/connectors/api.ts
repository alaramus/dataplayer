import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { AdaptersService, ConnectorsService } from "@/client"
import { waitingKey } from "@/features/shares/attention"
import type {
  AdapterTypeInfo,
  ConnectorCreate,
  ConnectorUpdate,
  ConnectorsPublic,
  MadeHereRequest,
} from "@/client"

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
 * A rename leaves every such copy behind. The current name belongs to the
 * connection rather than whichever tab first opened it.
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

/**
 * How long this connection keeps an answer, or nothing when its owner left
 * that to the source.
 *
 * Read out of the list by id, beside the name and the colour and for the same
 * reason: a window changed while a grid is open has to reach that grid, and a
 * copy taken when the panel opened would not (D105).
 */
export function connectorCacheWindowOf(
  connectors: ConnectorsPublic | undefined,
  connectorId: string | null
): number | null {
  if (connectorId === null) return null
  return (
    connectors?.data.find((one) => one.id === connectorId)?.cache_ttl_seconds ?? null
  )
}

/**
 * Whether an answer from this connection could ever be older than the read.
 *
 * Two ways to be no, and both count: a source that never opted into caching
 * keeps nothing whatever its owner typed, and an owner who chose to keep
 * nothing meant it. Unknown counts as no as well — the lists arrive a moment
 * after the panel, and a mark that appears is easier to read than one that
 * appears and goes away (D105).
 */
export function connectionKeepsAnswers(
  connectors: ConnectorsPublic | undefined,
  adapterTypes: AdapterTypeInfo[] | undefined,
  connectorId: string | null
): boolean {
  if (connectorId === null) return false
  const connector = connectors?.data.find((one) => one.id === connectorId)
  if (connector === undefined || connector.cache_ttl_seconds === 0) return false
  const adapterType = adapterTypes?.find(
    (one) => one.name === connector.adapter_type
  )
  return adapterType?.cache_windows != null
}

/**
 * What a screen showing data needs to know about how old it may be.
 *
 * One call rather than two queries and two lookups in every panel: whether
 * there is anything to say, and the window to say it against.
 */
export function useConnectionFreshness(connectorId: Ref<string>) {
  const connectors = useConnectors()
  const adapterTypes = useAdapterTypes()
  return {
    keepsAnswers: computed(() =>
      connectionKeepsAnswers(
        connectors.data.value,
        adapterTypes.data.value,
        connectorId.value
      )
    ),
    cacheWindow: computed(() =>
      connectorCacheWindowOf(connectors.data.value, connectorId.value)
    ),
  }
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

/** A new source made on this server, and its connection saved (D263). */
export function useMakeConnectorHere() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: MadeHereRequest) =>
      (await ConnectorsService.makeConnectorHere({ body })).data,
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
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: connectorsKey })
      // Deleting a connection takes its unanswered requests for access with
      // it, in the database (they cascade). The list of what is waiting is
      // read across every connection, so it is stale here and nowhere else,
      // and a request nobody can answer any more would sit in the activity
      // sheet until its next refresh (D113).
      await queryClient.invalidateQueries({ queryKey: waitingKey })
    },
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
 * A check of the connection as it is stored: all a grantee may ask, since a
 * draft leaning on the stored password is the owner's alone (D33).
 */
export function useCheckConnector() {
  return useMutation({
    mutationFn: async (connectorId: string) =>
      (await ConnectorsService.checkConnector({ path: { connector_id: connectorId } })).data,
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
 * Asked of the server because the rule for reading a DSN belongs to the
 * driver, which also names the way of connecting — a form deciding that from
 * the presence of a password would be a rule about authentication in a
 * component that knows none. Nothing is opened, and nothing is stored (V5, V7).
 */
export function useParseUrl() {
  return useMutation({
    mutationFn: async (body: { adapter_type: string; url: string }) =>
      (await ConnectorsService.parseUrl({ body })).data,
  })
}
