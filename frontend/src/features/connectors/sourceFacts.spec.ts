import { describe, expect, it } from "vitest"

import type { SourceFeatures } from "@/client"

import { sourceFacts } from "./sourceFacts"

const observed = "2026-09-08T12:00:00Z"

describe("what a source said about itself", () => {
  it("names the server first, then every installed extension once", () => {
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
      extensions: [
        { name: "timescaledb", version: "2.18.0" },
        { name: "vector", version: "0.8.0" },
      ],
    }

    expect(sourceFacts(said, "PostgreSQL")).toEqual([
      { code: "server", label: "PostgreSQL", value: "17.6" },
      { code: "extension-timescaledb", label: "TimescaleDB", value: "2.18.0" },
      { code: "extension-vector", label: "vector", value: "0.8.0" },
    ])
  })

  it("does not mention a feature whose extension is not installed", () => {
    const facts = sourceFacts(
      {
        observed_at: observed,
        server_version: "17.6",
        features: [{ code: "timescaledb", title: "TimescaleDB", state: "absent" }],
        extensions: [{ name: "pgcrypto", version: "1.3" }],
      },
      "PostgreSQL"
    )

    expect(facts.map((fact) => fact.code)).toEqual(["server", "extension-pgcrypto"])
  })

  it("says why an installed extension cannot be used, on its own line", () => {
    const facts = sourceFacts(
      {
        observed_at: observed,
        features: [
          {
            code: "timescaledb",
            title: "TimescaleDB",
            installed_version: "3.0.0",
            state: "unsupported",
            reason: "This TimescaleDB major version is not supported",
          },
        ],
        extensions: [{ name: "timescaledb", version: "3.0.0" }],
      },
      "PostgreSQL"
    )

    expect(facts).toEqual([
      {
        code: "extension-timescaledb",
        label: "TimescaleDB",
        value: "3.0.0",
        note: "This TimescaleDB major version is not supported",
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
