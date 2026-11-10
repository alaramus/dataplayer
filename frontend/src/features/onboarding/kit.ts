import type { QueryClient } from "@tanstack/vue-query"

import { ConnectorsService, PipelinesService } from "@/client"
import { connectorsKey } from "@/features/connectors/api"
import { pipelinesKey } from "@/features/pipelines/api"
import { t } from "@/shared/i18n"

import type { TourKit } from "./tour"

/**
 * The requests a short tour makes itself (D356): a practice database before
 * the person's part, the folder it writes into, and the database taken away
 * after. Plain requests rather than mutations with keys, so the tour never
 * mistakes its own work for the person's.
 */
export function tourKit(queryClient: QueryClient): TourKit {
  const refresh = () => queryClient.invalidateQueries({ queryKey: connectorsKey })

  /** The name, or the name and the first number no connection has. */
  async function freeName(base: string): Promise<string> {
    const listed = (await ConnectorsService.readConnectors()).data
    const taken = new Set(listed.data.map((connector) => connector.name))
    let name = base
    for (let number = 2; taken.has(name); number += 1) name = `${base}-${number}`
    return name
  }

  return {
    async makePractice() {
      // A name of its own: the chapters find the connection by it, and one
      // left from an earlier run must not be the one ringed.
      const name = await freeName(t("onboarding.tours.practice_name"))
      const made = (
        await ConnectorsService.makeConnectorHere({
          body: { adapter_type: "sqlite", choice: { name } },
        })
      ).data
      await refresh()
      const path = typeof made.config.path === "string" ? made.config.path : ""
      return { id: made.id, name: made.name, path }
    },

    async ensureFolder() {
      const listed = (await ConnectorsService.readConnectors()).data
      const own = listed.data.find(
        (connector) =>
          connector.adapter_type === "file" &&
          connector.access === "own" &&
          (connector.config.path === "/" || connector.config.path === "")
      )
      if (own !== undefined) return { id: own.id, name: own.name }
      const name = await freeName(t("onboarding.tours.folder_name"))
      const made = (
        await ConnectorsService.createConnector({
          body: { name, adapter_type: "file", options: { path: "/" } },
        })
      ).data
      await refresh()
      return { id: made.id, name: made.name }
    },

    async removeWithFile(connectorId: string) {
      await ConnectorsService.deleteConnector({
        path: { connector_id: connectorId },
        query: { with_file: true },
      })
      await refresh()
    },

    async removePipeline(pipelineId: string) {
      await PipelinesService.deletePipeline({ path: { pipeline_id: pipelineId } })
      await queryClient.invalidateQueries({ queryKey: pipelinesKey })
    },
  }
}
