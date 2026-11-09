import { describe as suite, expect, it } from "vitest"

import type { NodeSummary } from "@/client"

import { describe } from "./facts"

function summary(over: Partial<NodeSummary> = {}): NodeSummary {
  return {
    node_id: "notes.txt",
    name: "notes.txt",
    kind: "file",
    representations: [{ kind: "text", title: "View as text" }],
    size_bytes: 2048,
    modified_at: "2026-09-02T10:00:00Z",
    permissions: "-rw-r--r--",
    ...over,
  }
}

function labelled(facts: { label: string; value: string }[], label: string) {
  return facts.find((fact) => fact.label === label)?.value
}

suite("describe", () => {
  it("states what every node has, in the source's own words", () => {
    const described = describe(summary())

    expect(labelled(described.facts, "Kind")).toBe("File")
    expect(labelled(described.facts, "Size")).toBe("2.0 KB")
    expect(labelled(described.facts, "Permissions")).toBe("-rw-r--r--")
    // The source wrote the title of the view; this screen only joins them.
    expect(labelled(described.facts, "Opens as")).toBe("View as text")
  })

  it("prints a topic's partitions and its own settings (D305)", () => {
    const described = describe(
      summary({
        node_id: "topic:orders",
        name: "orders",
        kind: "topic",
        size_bytes: null,
        modified_at: null,
        permissions: null,
        contents: {
          kind: "kafka_topic",
          messages: 42,
          partitions: [
            { partition: 0, leader: 1, replicas: [1, 2], in_sync: [1], first_offset: 0, end_offset: 42 },
          ],
          settings: [
            { name: "retention.ms", value: "86400000" },
            { name: "sasl.jaas.config", value: null },
          ],
        },
      })
    )

    expect(labelled(described.facts, "Kind")).toBe("Topic")
    expect(labelled(described.contents, "Messages")).toBe("42")
    expect(labelled(described.contents, "Partition 0")).toBe(
      "leader 1, replicas 1, 2, in sync 1, offsets 0–42"
    )
    expect(labelled(described.contents, "retention.ms")).toBe("86400000")
    expect(labelled(described.contents, "sasl.jaas.config")).toBe("hidden by the broker")
  })

  it("prints where a consumer group stands (D305)", () => {
    const described = describe(
      summary({
        node_id: "group:billing",
        name: "billing",
        kind: "consumer_group",
        size_bytes: null,
        modified_at: null,
        permissions: null,
        contents: {
          kind: "kafka_group",
          state: "empty",
          members: 0,
          coordinator: 1,
          topics: ["orders", "refunds"],
          lag: 7,
        },
      })
    )

    expect(labelled(described.contents, "State")).toBe("no consumers")
    expect(labelled(described.contents, "Lag")).toBe("7")
    expect(labelled(described.contents, "Topics")).toBe("orders, refunds")
    expect(labelled(described.contents, "Assignor")).toBeUndefined()
  })

  it("prints what waits in a RabbitMQ queue and who takes it (D326)", () => {
    const described = describe(
      summary({
        node_id: "queue:%2F/billing",
        name: "billing",
        kind: "amqp_queue",
        size_bytes: null,
        modified_at: null,
        permissions: null,
        contents: {
          kind: "amqp_queue",
          queue_type: "quorum",
          state: "running",
          ready: 3,
          unacknowledged: 1,
          rate_in: 2.25,
          rate_out: null,
          node: "rabbit@one",
          policy: null,
          arguments: [{ name: "x-queue-type", value: "quorum" }],
          consumers: [{ tag: "ctag-1", channel: "10.0.0.5:50000 (1)", prefetch: 10, acknowledges: false }],
        },
      })
    )

    expect(labelled(described.facts, "Kind")).toBe("Queue")
    expect(labelled(described.contents, "Type")).toBe("quorum")
    expect(labelled(described.contents, "Ready")).toBe("3")
    expect(labelled(described.contents, "In")).toBe("2.3/s")
    expect(labelled(described.contents, "Out")).toBeUndefined()
    expect(labelled(described.contents, "Policy")).toBeUndefined()
    expect(labelled(described.contents, "Consumer ctag-1")).toBe(
      "10.0.0.5:50000 (1), prefetch 10, no acknowledgement"
    )
    expect(labelled(described.contents, "x-queue-type")).toBe("quorum")
  })

  it("prints an exchange's type and flags (D326)", () => {
    const described = describe(
      summary({
        node_id: "exchange:%2F/dp.orders",
        name: "dp.orders",
        kind: "exchange",
        size_bytes: null,
        modified_at: null,
        permissions: null,
        contents: { kind: "amqp_exchange", exchange_type: "topic", durable: true, internal: false },
      })
    )

    expect(labelled(described.facts, "Kind")).toBe("Exchange")
    expect(labelled(described.contents, "Type")).toBe("topic")
    expect(labelled(described.contents, "Durable")).toBe("Yes")
    expect(labelled(described.contents, "Internal")).toBe("No")
  })

  it("prints a znode's stat and one line per entry of its ACL (D298)", () => {
    const described = describe(
      summary({
        node_id: "/app",
        name: "app",
        kind: "znode",
        contents: {
          kind: "znode",
          version: 4,
          child_version: 2,
          acl_version: 0,
          created_zxid: "0x1a",
          modified_zxid: "0x2b",
          children_zxid: "0x2c",
          children: 2,
          ephemeral_owner: "0x100000abc",
          acl: [
            { scheme: "world", id: "anyone", permissions: ["read"] },
            { scheme: "digest", id: "ann:hash", permissions: [] },
          ],
        },
      })
    )

    expect(labelled(described.facts, "Kind")).toBe("Znode")
    expect(labelled(described.contents, "Version")).toBe("4")
    expect(labelled(described.contents, "Created zxid")).toBe("0x1a")
    expect(labelled(described.contents, "Ephemeral owner")).toBe("0x100000abc")
    expect(described.contents.filter((fact) => fact.label === "ACL").map((fact) => fact.value)).toEqual([
      "world:anyone — read",
      "digest:ann:hash — none",
    ])
  })

  it("leaves out a time the platform did not state", () => {
    const described = describe(summary({ created_at: null, accessed_at: null }))

    expect(labelled(described.facts, "Created")).toBeUndefined()
    expect(labelled(described.facts, "Opened")).toBeUndefined()
    expect(labelled(described.facts, "Modified")).toBeDefined()
  })

  it("says so when a file has no viewer, rather than saying nothing", () => {
    const described = describe(summary({ name: "app.exe", representations: [] }))

    expect(labelled(described.facts, "Opens as")).toBe("Nothing this source can show")
  })

  it("does not ask a folder what it opens as", () => {
    const described = describe(
      summary({
        kind: "directory",
        representations: [],
        size_bytes: null,
        contents: { kind: "directory", entries: 3, files: 2, directories: 1 },
      })
    )

    expect(labelled(described.facts, "Opens as")).toBeUndefined()
    expect(labelled(described.contents, "Files")).toBe("2")
    expect(labelled(described.contents, "Folders")).toBe("1")
  })

  it("prints what a text file states about its lines", () => {
    const described = describe(
      summary({
        contents: {
          kind: "text",
          encoding: "utf-8-bom",
          lines: 120,
          longest_line_bytes: 4096,
          line_endings: "crlf",
        },
      })
    )

    expect(labelled(described.contents, "Encoding")).toBe("UTF-8 with a byte order mark")
    expect(labelled(described.contents, "Lines")).toBe("120")
    expect(labelled(described.contents, "Longest line")).toBe("4.0 KB")
    expect(labelled(described.contents, "Line endings")).toBe("CRLF (Windows)")
    expect(described.notice).toBeNull()
  })

  it("shows a count that hit a ceiling as absent with its reason", () => {
    const described = describe(
      summary({
        contents: {
          kind: "text",
          encoding: "utf-8",
          lines: null,
          not_counted: "This file is larger than 32 MB and was not read through",
        },
      })
    )

    // Absent, never a zero: a zero would read as a measurement.
    expect(labelled(described.contents, "Lines")).toBeUndefined()
    expect(described.notice).toContain("32 MB")
  })

  it("carries the source's refusal when the bytes are not the promised format", () => {
    const described = describe(
      summary({
        name: "forged.png",
        contents: null,
        notice: "This file is not a valid PNG or JPEG image",
        representations: [{ kind: "image", title: "View image" }],
      })
    )

    expect(described.contents).toEqual([])
    expect(described.notice).toBe("This file is not a valid PNG or JPEG image")
    // The facts that are still true survive the format that is not.
    expect(labelled(described.facts, "Size")).toBe("2.0 KB")
  })

  it("prints a dataset with the function that already prints one", () => {
    const described = describe(
      summary({
        name: "cities.parquet",
        contents: {
          kind: "parquet",
          rows: 3,
          row_groups: 1,
          columns: 2,
          compression: ["SNAPPY"],
          format_version: "2.6",
          size_bytes: 1024,
        },
      })
    )

    expect(labelled(described.contents, "Format")).toBe("Parquet 2.6")
    expect(labelled(described.contents, "Rows")).toBe("3")
  })

  it("counts an archive from what it declares", () => {
    const described = describe(
      summary({
        name: "bundle.zip",
        contents: {
          kind: "archive",
          entries: 4,
          files: 3,
          directories: 1,
          size_bytes: 4096,
          compressed_bytes: 1024,
          encrypted: 0,
          links: 0,
        },
      })
    )

    expect(labelled(described.contents, "Unpacked")).toBe("4.0 KB")
    expect(labelled(described.contents, "Packed")).toBe("1.0 KB")
    // Zero of either is not a fact worth a line.
    expect(labelled(described.contents, "Encrypted entries")).toBeUndefined()
    expect(labelled(described.contents, "Links")).toBeUndefined()
  })

  it("names a delimiter rather than printing the character", () => {
    const described = describe(
      summary({
        name: "people.tsv",
        contents: {
          kind: "delimited",
          delimiter: "tab",
          columns: 3,
          rows: 42,
          encoding: "utf-8",
        },
      })
    )

    expect(labelled(described.contents, "Separated by")).toBe("tab")
    expect(labelled(described.contents, "Rows")).toBe("42")
  })

  it("says what a recording states and leaves out what it does not", () => {
    const described = describe(
      summary({
        name: "clip.mp4",
        contents: {
          kind: "video",
          media_type: "video/mp4",
          duration_seconds: 125,
          width: 1920,
          height: 1080,
        },
      })
    )

    expect(labelled(described.contents, "Format")).toBe("MP4")
    expect(labelled(described.contents, "Duration")).toBe("2:05")
    expect(labelled(described.contents, "Size")).toBe("1920 × 1080")
  })

  it("shows what a table is made of, without repeating its kind", () => {
    const described = describe(
      summary({
        kind: "table",
        name: "orders",
        size_bytes: 4096,
        representations: [{ kind: "table", title: "View as table" }],
        contents: {
          kind: "relation",
          relation_kind: "table",
          schema_name: "demo_lab",
          owner: "app",
          persistence: "permanent",
          columns: 9,
          indexes: 2,
          constraints: 3,
          row_estimate: 1200,
          analyzed_at: "2026-09-02T10:00:00Z",
        },
      })
    )

    expect(labelled(described.facts, "Kind")).toBe("Table")
    expect(labelled(described.contents, "Schema")).toBe("demo_lab")
    expect(labelled(described.contents, "Owner")).toBe("app")
    expect(labelled(described.contents, "Columns")).toBe("9")
    expect(labelled(described.contents, "Indexes")).toBe("2")
    expect(labelled(described.contents, "Rows")).toBe("~1200")
    expect(labelled(described.contents, "Analysed")).toBeDefined()
    // Two lines that would say what the line above them already says: an
    // ordinary table is a table, and every table is permanent.
    expect(labelled(described.contents, "Stored as")).toBeUndefined()
    expect(labelled(described.contents, "Storage")).toBeUndefined()
  })

  it("says how a relation is stored where the kind does not", () => {
    const described = describe(
      summary({
        kind: "view",
        name: "rollup",
        contents: {
          kind: "relation",
          relation_kind: "materialized_view",
          schema_name: "demo_lab",
          persistence: "unlogged",
          columns: 4,
          indexes: 1,
          constraints: 0,
          row_estimate: null,
        },
      })
    )

    expect(labelled(described.facts, "Kind")).toBe("View")
    expect(labelled(described.contents, "Stored as")).toBe("Materialized view")
    expect(labelled(described.contents, "Storage")).toBe("Unlogged")
    // Said even where there is no number, as the catalog says it.
    expect(labelled(described.contents, "Rows")).toBe("Not estimated")
  })

  it("shows an entry's own facts, which are the archive's", () => {
    const described = describe(
      summary({
        kind: "entry",
        name: "notes.txt",
        contents: { kind: "entry", compressed_bytes: 512, encrypted: false, link: false },
      })
    )

    expect(labelled(described.facts, "Kind")).toBe("Archive entry")
    expect(labelled(described.contents, "Packed")).toBe("512 B")
    expect(labelled(described.contents, "Encrypted")).toBeUndefined()
  })
})
