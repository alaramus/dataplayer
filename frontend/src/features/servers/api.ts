import { useQuery } from "@tanstack/vue-query"
import type { MaybeRefOrGetter } from "vue"

import { UtilsService } from "@/client"
import { createClient } from "@/client/client"
import { serverContext } from "@/shared/servers/context"
import { normalizeServerUrl } from "@/shared/servers/profiles"

export async function checkServer(address: string, signal?: AbortSignal): Promise<true> {
  const url = normalizeServerUrl(address)
  if (window.location.protocol === "https:" && new URL(url).protocol === "http:") {
    throw new Error("This page uses HTTPS. Use an HTTPS server address.")
  }
  // An isolated client: never the signed-in client's auth callback or interceptors.
  const anonymous = createClient({
    baseURL: url,
    adapter: "fetch",
    withCredentials: false,
    fetchOptions: { redirect: "error" },
    timeout: 7000,
    throwOnError: true,
  })
  let data: unknown
  try {
    const response = await UtilsService.serverInfo({ client: anonymous, signal })
    data = response.data
  } catch {
    throw new Error("Could not reach a compatible DataPlayer server. Check the address, server version, certificate and allowed frontend origin (CORS).")
  }
  if (data === null || typeof data !== "object" ||
      !("product" in data) || data.product !== "dataplayer" ||
      !("client_api_version" in data) || data.client_api_version !== 1) {
    throw new Error("This server is not compatible with this version of DataPlayer.")
  }
  return true
}

export function serverCheckOptions(url: string) {
  return {
    queryKey: ["servers", "compatibility", url],
    queryFn: ({ signal }: { signal: AbortSignal }) => checkServer(url, signal),
    retry: false as const,
    staleTime: Infinity,
  }
}

export function useActiveServerCheck(enabled: MaybeRefOrGetter<boolean> = true) {
  return useQuery({ ...serverCheckOptions(serverContext().active.url), enabled })
}
