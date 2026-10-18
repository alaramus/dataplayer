import { describe, expect, it } from "vitest"

import type { AgentRunPublic } from "@/client"
import { unansweredEnds } from "./endedRuns"

const run = (id: string, status: AgentRunPublic["status"]): AgentRunPublic => ({
  id,
  conversation_id: "c1",
  status,
  model_key: "gemini-3.1-flash-lite",
  error: status === "failed" ? "The provider refused the request · ref E84ZH7" : null,
})

describe("runs that ended without an answer", () => {
  it("keeps a run that failed before a word of the answer, though the question carries its id", () => {
    const failed = run("r1", "failed")
    expect(unansweredEnds([{ role: "user", run_id: "r1" }], [failed])).toEqual([failed])
  })

  it("leaves a run whose answer is there to the answer", () => {
    const failed = run("r1", "failed")
    const messages = [{ role: "user", run_id: "r1" }, { role: "assistant", run_id: "r1" }] as const
    expect(unansweredEnds(messages, [failed])).toEqual([])
  })

  it("says nothing about a run that is still going or went well", () => {
    const messages = [{ role: "user", run_id: "r1" }, { role: "user", run_id: "r2" }] as const
    expect(unansweredEnds(messages, [run("r1", "running"), run("r2", "succeeded")])).toEqual([])
  })
})
