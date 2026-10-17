import { useQuery } from "@tanstack/vue-query"
import type { MaybeRefOrGetter } from "vue"

import { UtilsService } from "@/client"
import { createClient } from "@/client/client"
import { t } from "@/shared/i18n"
import { serverContext } from "@/shared/servers/context"
import { normalizeServerUrl } from "@/shared/servers/profiles"

export async function checkServer(address: string, signal?: AbortSignal): Promise<true> {
  const url = normalizeServerUrl(address)
  if (window.location.protocol === "https:" && new URL(url).protocol === "http:") {
    throw new Error(t("servers.check.https_only"))
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
    throw new Error(t("servers.check.unreachable"))
  }
  if (data === null || typeof data !== "object" ||
      !("product" in data) || data.product !== "dataplayer" ||
      !("client_api_version" in data) || data.client_api_version !== 1) {
    throw new Error(t("servers.check.incompatible"))
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
