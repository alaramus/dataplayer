import { describe, expect, it } from "vitest"

import type { SourceFeatures } from "@/client"

import { sourceFacts } from "./sourceFacts"

const observed = "2026-09-08T12:00:00Z"

describe("what a source said about itself", () => {
  it("names the server first, in the words of its own type", () => {
    const said: SourceFeatures = {
      observed_at: observed,
      server_version: "17.6",
      features: [
        {
          code: "timescaledb",
          title: "TimescaleDB",
          installed_version: "2.18.0",
          state: "available",
        },
      ],
    }

    expect(sourceFacts(said, "PostgreSQL")).toEqual([
      { code: "server", label: "PostgreSQL", value: "17.6" },
      {
        code: "timescaledb",
        label: "TimescaleDB",
        value: "2.18.0 — Available for inspection",
      },
    ])
  })

  it("says a plain server is a plain server, with nothing installed", () => {
    // The reason this moved out of Options: somebody connecting to a database
    // with no extension at all still wants to know what they are working on.
    const facts = sourceFacts(
      { observed_at: observed, server_version: "7.4.1", features: [] },
      "Redis"
    )

    expect(facts).toEqual([{ code: "server", label: "Redis", value: "7.4.1" }])
  })

  it("keeps the reason a feature could not be inspected", () => {
    const [fact] = sourceFacts(
      {
        observed_at: observed,
        features: [
          {
            code: "timescaledb",
            title: "TimescaleDB",
            state: "unavailable",
            reason: "This connection may not inspect installed extensions",
          },
        ],
      },
      "PostgreSQL"
    )

    expect(fact?.value).toBe("Inspection unavailable")
    expect(fact?.note).toContain("may not inspect")
  })

  it("has nothing to show for a source that says nothing", () => {
    expect(sourceFacts(null, "Files")).toEqual([])
    expect(sourceFacts(undefined, "Files")).toEqual([])
    expect(
      sourceFacts({ observed_at: observed, features: [] }, "Files")
    ).toEqual([])
  })
})
