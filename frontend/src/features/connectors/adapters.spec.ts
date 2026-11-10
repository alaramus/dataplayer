import { describe, expect, it } from "vitest"

import { adapterIcon, categoryIcon, connectorIcon, UNKNOWN_CATEGORY_ICON, UNKNOWN_ADAPTER_ICON } from "./adapters"

describe("the icon of a source type", () => {
  it("tells the types apart", () => {
    const drawn = ["postgres", "mongodb", "redis", "zookeeper", "kafka", "rabbitmq", "binance", "file", "ssh"].map(adapterIcon)
    expect(new Set(drawn).size).toBe(drawn.length)
  })

  it("names a file under the icons served with the app", () => {
    expect(adapterIcon("postgres")).toBe("img:/icons/services/postgresql.svg")
  })

  it("draws MariaDB as itself, though it is a card of the mysql type (D264)", () => {
    expect(adapterIcon("mariadb")).toBe("img:/icons/services/mariadb.svg")
    expect(adapterIcon("mariadb")).not.toBe(adapterIcon("mysql"))
  })

  it("draws ScyllaDB as itself, though it is a card of the cassandra type (D340)", () => {
    expect(adapterIcon("scylladb")).toBe("img:/icons/services/scylladb.svg")
    expect(adapterIcon("cassandra")).toBe("img:/icons/services/cassandra.svg")
  })

  it("falls back for a type the backend gained since this build", () => {
    expect(adapterIcon("zeromq")).toBe(UNKNOWN_ADAPTER_ICON)
  })
})

describe("the glyph of a category", () => {
  it("gives each group its own", () => {
    const drawn = ["sql", "document", "keyvalue", "stream", "market", "files"].map(categoryIcon)
    expect(new Set(drawn).size).toBe(drawn.length)
  })

  it("falls back for a group the backend gained since this build", () => {
    expect(categoryIcon("timeseries")).toBe(UNKNOWN_CATEGORY_ICON)
  })
})

describe("connectorIcon", () => {
  it("draws a connection as the card it was made from, and its type when it names none (D264)", () => {
    expect(connectorIcon({ adapter_type: "cassandra", face: "scylladb" })).toBe("img:/icons/services/scylladb.svg")
    expect(connectorIcon({ adapter_type: "mysql", face: "mariadb" })).toBe("img:/icons/services/mariadb.svg")
    expect(connectorIcon({ adapter_type: "mysql", face: null })).toBe("img:/icons/services/mysql.svg")
    expect(connectorIcon({ adapter_type: "postgres" })).toBe("img:/icons/services/postgresql.svg")
  })
})
