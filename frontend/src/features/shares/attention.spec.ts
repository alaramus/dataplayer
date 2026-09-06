import { describe, expect, it, vi } from "vitest"

import type { AccessRequestPublic } from "@/client"
import { requestItem } from "./attention"

const asked: AccessRequestPublic = {
  id: "req-1",
  connector_id: "conn-1",
  connector_label: "prod-db",
  requester_id: "user-1",
  requester_email: "ivan@example.com",
  requester_name: "Ivan",
  node_label: "orders",
  state: "pending",
  created_at: "2026-09-06T09:00:00Z",
}

describe("somebody waiting for access", () => {
  it("is named by the person and the connection, because neither alone is enough to act on", () => {
    expect(requestItem(asked, () => {}).title).toBe("Ivan is asking for access to prod-db")
  })

  it("falls back to the address when nobody filled in a name", () => {
    const anonymous = { ...asked, requester_name: null }

    expect(requestItem(anonymous, () => {}).title).toContain("ivan@example.com")
  })

  it("leads to the connection rather than answering in place", () => {
    const answer = vi.fn()

    requestItem(asked, answer).action?.run()

    expect(answer).toHaveBeenCalledWith("conn-1")
  })

  it("cannot be waved away: the other person is still waiting", () => {
    expect(requestItem(asked, () => {}).dismiss).toBeNull()
  })
})
