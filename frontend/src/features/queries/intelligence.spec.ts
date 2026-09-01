import { describe, expect, it } from "vitest"

import type { PreparedScript, QueryMetadata } from "@/client"

import { marks, metadataStatus, relationsInUse, suggestions } from "./intelligence"

const METADATA: QueryMetadata = {
  schemas: ["public", "sales"],
  relations: [
    { schema_name: "public", name: "orders", kind: "table" },
    { schema_name: "public", name: "people", kind: "view" },
    { schema_name: "sales", name: "orders", kind: "table" },
  ],
  columns: {
    "public.orders": [
      { name: "id", type_sql: "bigint" },
      { name: "total", type_sql: "numeric" },
    ],
  },
  complete: true,
}

function script(
  ...statements: {
    kind: string
    targets?: string[]
    start?: number
    end?: number
    parameters?: string[]
  }[]
): PreparedScript {
  return {
    statements: statements.map((statement, ordinal) => ({
      ordinal,
      start: statement.start ?? ordinal * 10,
      end: statement.end ?? ordinal * 10 + 8,
      text: "select 1",
      kind: statement.kind as PreparedScript["statements"][number]["kind"],
      parameters: statement.parameters ?? [],
      targets: statement.targets ?? [],
    })),
    parameters: statements.flatMap((statement) => statement.parameters ?? []),
  }
}

describe("what the editor offers", () => {
  it("offers schemas, relations and the columns it has been told about", () => {
    const offered = suggestions(METADATA, null)
    const labels = offered.map((suggestion) => suggestion.label)

    expect(labels).toContain("public")
    expect(labels).toContain("public.orders")
    expect(labels).toContain("id")
    expect(labels).toContain("total")
  })

  it("offers a bare name only when it means one thing", () => {
    const labels = suggestions(METADATA, null).map((suggestion) => suggestion.label)

    // `orders` is in two schemas, so only the qualified forms are offered.
    expect(labels).not.toContain("orders")
    expect(labels).toContain("people")
    expect(labels).toContain("sales.orders")
  })

  it("offers the parameters the source found in the text", () => {
    const offered = suggestions(METADATA, script({ kind: "read", parameters: ["since"] }))

    expect(offered).toContainEqual({
      label: ":since",
      detail: "parameter",
      kind: "parameter",
    })
  })

  it("offers nothing at all before the source has answered", () => {
    expect(suggestions(undefined, null)).toEqual([])
  })

  it("asks about the relations the text names, and no others", () => {
    expect(
      relationsInUse(script({ kind: "read", targets: ["public.orders", "people"] }))
    ).toEqual(["public.orders", "people"])
    expect(relationsInUse(null)).toEqual([])
  })
})

describe("what the editor dares mark", () => {
  it("marks a statement it could not read, as a warning about itself", () => {
    const found = marks(script({ kind: "unknown" }), METADATA)

    expect(found).toHaveLength(1)
    expect(found[0]).toMatchObject({ severity: "warning" })
    expect(found[0]?.message).toContain("could not be read")
  })

  it("marks a statement this connection will not run", () => {
    const found = marks(script({ kind: "dml" }), METADATA)

    expect(found[0]?.message).toContain("dml")
  })

  it("marks a qualified name the source does not have", () => {
    const found = marks(script({ kind: "read", targets: ["public.nothing"] }), METADATA)

    expect(found).toHaveLength(1)
    expect(found[0]?.message).toBe("public has nothing called nothing")
  })

  it("says nothing about a bare name, which may be a CTE or an alias", () => {
    expect(marks(script({ kind: "read", targets: ["recent"] }), METADATA)).toEqual([])
  })

  it("says nothing about a schema it was never told about", () => {
    expect(
      marks(script({ kind: "read", targets: ["other.orders"] }), METADATA)
    ).toEqual([])
  })

  it("says nothing at all while the metadata is incomplete", () => {
    const partial: QueryMetadata = { ...METADATA, complete: false }

    expect(marks(script({ kind: "read", targets: ["public.nothing"] }), partial)).toEqual(
      []
    )
  })

  it("says nothing before the source has answered", () => {
    expect(marks(script({ kind: "read", targets: ["public.nothing"] }), undefined)).toEqual(
      []
    )
    expect(marks(null, METADATA)).toEqual([])
  })

  it("marks the range the source gave, so it points at the statement", () => {
    const found = marks(
      script({ kind: "unknown", start: 12, end: 30 }),
      METADATA
    )

    expect(found[0]).toMatchObject({ from: 12, to: 30 })
  })
})

describe("what the console says about how much it knows", () => {
  it("says it is still reading before an answer", () => {
    expect(metadataStatus(undefined)).toContain("Reading")
  })

  it("says so when the source held more than it offered", () => {
    expect(metadataStatus({ ...METADATA, complete: false })).toContain("more relations")
  })

  it("says nothing when it knows everything it needs to", () => {
    expect(metadataStatus(METADATA)).toBe("")
  })
})
