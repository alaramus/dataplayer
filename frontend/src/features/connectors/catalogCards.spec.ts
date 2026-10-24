import { describe, expect, it } from "vitest"

import type { AdapterTypeInfo, ServiceTemplateInfo } from "@/client"

import { cardsOf, templatesOf } from "./catalogCards"

function type(name: string, title: string, faces: AdapterTypeInfo["faces"] = []): AdapterTypeInfo {
  return { name, title, category: "sql", category_title: "SQL", faces } as AdapterTypeInfo
}

function template(key: string, adapterType: string): ServiceTemplateInfo {
  return { key, adapter_type: adapterType, title: key } as ServiceTemplateInfo
}

const MYSQL = type("mysql", "MySQL", [
  { key: "mysql", title: "MySQL", templates: ["mysql"] },
  { key: "mariadb", title: "MariaDB", templates: ["mariadb"] },
])
const POSTGRES = type("postgres", "PostgreSQL")
const STARTABLE = [
  template("postgres", "postgres"),
  template("timescale", "postgres"),
  template("mysql", "mysql"),
  template("mariadb", "mysql"),
]

describe("the cards of the catalog of types (D264)", () => {
  it("shows a type as itself, and one that speaks to several products as a card each", () => {
    const cards = cardsOf([POSTGRES, MYSQL])

    expect(cards.map((card) => [card.key, card.title, card.type.name])).toEqual([
      ["postgres", "PostgreSQL", "postgres"],
      ["mysql", "MySQL", "mysql"],
      ["mariadb", "MariaDB", "mysql"],
    ])
  })

  it("offers each card its own server, and a type of one card every server of it", () => {
    const [postgres, mysql, mariadb] = cardsOf([POSTGRES, MYSQL])

    expect(templatesOf(postgres!, STARTABLE).map((one) => one.key)).toEqual(["postgres", "timescale"])
    expect(templatesOf(mysql!, STARTABLE).map((one) => one.key)).toEqual(["mysql"])
    expect(templatesOf(mariadb!, STARTABLE).map((one) => one.key)).toEqual(["mariadb"])
  })
})
