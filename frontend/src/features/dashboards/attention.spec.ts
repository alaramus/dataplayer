import { describe, expect, it, vi } from "vitest"

import type { HostRestarts } from "@/client"
import { restartItem } from "./attention"

const crashing: HostRestarts = {
  agent_id: "agent-1",
  agent_name: "office",
  host: "crash-probe",
  count: 27,
  first_at: "2026-09-13T11:25:00Z",
  last_at: "2026-09-13T11:40:00Z",
  cause: "agent",
}

describe("a host that keeps restarting", () => {
  it("is named by its host and counted over the server's window", () => {
    const item = restartItem(crashing, 900, () => {})

    expect(item.title).toBe("crash-probe keeps restarting")
    expect(item.detail).toBe("The agent office started again 27 times in the last 15 minutes; its log says why.")
    expect(item.at).toBe(Date.parse("2026-09-13T11:40:00Z"))
  })

  it("says the host itself booted when its boot changed with the agent", () => {
    const detail = restartItem({ ...crashing, cause: "host" }, 900, () => {}).detail

    expect(detail).toBe("The host booted 27 times in the last 15 minutes, by what office reports.")
  })

  it("opens the dashboards and cannot be waved away while it goes on", () => {
    const open = vi.fn()
    const item = restartItem(crashing, 900, open)

    item.action?.run()

    expect(open).toHaveBeenCalled()
    expect(item.dismiss).toBeNull()
    expect(item.tone).toBe("warning")
  })
})
