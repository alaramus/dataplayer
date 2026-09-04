import { afterEach, describe, expect, it, vi } from "vitest"

import { UtilsService } from "@/client"
import { client } from "@/client/client.gen"
import { checkServer } from "./api"

afterEach(() => vi.restoreAllMocks())

describe("anonymous compatibility checks", () => {
  it("uses an isolated client with no current auth or cookies and a bounded request", async () => {
    const probe = vi.spyOn(UtilsService, "serverInfo").mockResolvedValue({ data: { product: "dataplayer", client_api_version: 1 } } as never)
    const controller = new AbortController()
    expect(await checkServer("https://other.example/player", controller.signal)).toBe(true)
    const options = probe.mock.calls[0]?.[0]
    expect(options?.client).not.toBe(client)
    expect(options?.client?.getConfig()).toMatchObject({ baseURL: "https://other.example/player", withCredentials: false, timeout: 7000, adapter: "fetch", fetchOptions: { redirect: "error" } })
    expect(options?.client?.getConfig().auth).toBeUndefined()
    expect(options?.signal).toBe(controller.signal)
  })

  it.each([null, "<html>login</html>", { product: "other", client_api_version: 1 }, { product: "dataplayer", client_api_version: 2 }])("refuses an incompatible response: %j", async (data) => {
    vi.spyOn(UtilsService, "serverInfo").mockResolvedValue({ data } as never)
    await expect(checkServer("https://other.example")).rejects.toThrow("not compatible")
  })

  it("reports a network failure without exposing transport internals", async () => {
    vi.spyOn(UtilsService, "serverInfo").mockRejectedValue(new Error("private transport detail"))
    await expect(checkServer("https://other.example")).rejects.toThrow("allowed frontend origin (CORS)")
  })
})
