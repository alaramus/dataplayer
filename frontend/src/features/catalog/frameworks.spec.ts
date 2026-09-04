import { describe, expect, it } from "vitest"

import type { DetectedFramework } from "@/client"
import { frameworksOf, toggleFrameworkFilter } from "./frameworks"
import { toListNodes } from "./nodes"

const django: DetectedFramework = {
  id: "django",
  title: "Django",
  table_filter: "django_",
}
const alembic: DetectedFramework = {
  id: "alembic",
  title: "Alembic",
  table_filter: "alembic_version",
}
const groups = toListNodes([
  {
    kind: "schema",
    id: "one",
    name: "one",
    has_children: true,
    representations: [],
    frameworks: [django, alembic],
  },
  {
    kind: "schema",
    id: "two",
    name: "two",
    has_children: true,
    representations: [],
    frameworks: [django],
  },
  {
    kind: "schema",
    id: "unknown",
    name: "unknown",
    has_children: true,
    representations: [],
  },
])

describe("source-issued framework hints", () => {
  it("keeps every match in selected schemas and merges duplicates", () => {
    expect(frameworksOf(groups, ["one", "two"])).toEqual([alembic, django])
    expect(frameworksOf(groups, ["two"])).toEqual([django])
    expect(frameworksOf(groups, ["unknown"])).toEqual([])
    expect(frameworksOf(groups, [])).toEqual([])
  })

  it("uses the source's filter, including an unfamiliar pattern", () => {
    const customized = { ...django, table_filter: "custom_marker" }
    expect(toggleFrameworkFilter("orders", customized)).toBe("custom_marker")
    expect(toggleFrameworkFilter("custom_marker", customized)).toBe("")
    expect(toggleFrameworkFilter("", django)).toBe("django_")
    expect(toggleFrameworkFilter("django_", alembic)).toBe("alembic_version")
  })
})
