import { describe, expect, it } from "vitest"

import { symbolIcon } from "./symbolIcons"

describe("Symbols Outlined icon mapping", () => {
  it("maps available ligatures and leaves special names alone", () => {
    expect(symbolIcon("dashboard")).toEqual({ icon: "sym_o_dashboard" })
    expect(symbolIcon("delete")).toEqual({ icon: "sym_o_delete" })
    expect(symbolIcon("not_an_icon")).toBeUndefined()
    expect(symbolIcon("img:/icons/source.svg")).toBeUndefined()
    expect(symbolIcon("sym_o_add")).toBeUndefined()
  })
})
