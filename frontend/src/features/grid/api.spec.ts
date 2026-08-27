import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import type { FetchRequest, FetchResult } from "@/client"

import { fetchRowsPage, rowsKey } from "./api"

const REQUEST: FetchRequest = {
  node_id: "public.projects",
  limit: 100,
  offset: 200,
  filters: [{ column: "status", op: "eq", value: "active" }],
  sort: [{ column: "name", descending: false }],
}

const RESULT: FetchResult = {
  columns: [],
  rows: [],
  has_more: false,
}

beforeEach(() => vi.restoreAllMocks())

describe("a rows page query", () => {
  it("keys a page by the complete server request", () => {
    expect(rowsKey("connector-1", REQUEST)).toEqual(["rows", "connector-1", REQUEST])
  })

  it("passes Vue Query's abort signal to the generated client", async () => {
    const fetchRows = vi
      .spyOn(ConnectorsService, "fetchRows")
      .mockResolvedValue({ data: RESULT } as never)
    const signal = new AbortController().signal

    await fetchRowsPage("connector-1", REQUEST, signal)

    expect(fetchRows).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: REQUEST,
      signal,
    })
  })
})
