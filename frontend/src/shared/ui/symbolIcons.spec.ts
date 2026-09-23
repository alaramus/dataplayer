import { describe, expect, it } from "vitest"

import { symbolIcon } from "./symbolIcons"

describe("Symbols Outlined icon mapping", () => {
  it("maps available ligatures and leaves legacy or special names alone", () => {
    expect(symbolIcon("dashboard")).toEqual({ icon: "sym_o_dashboard" })
    expect(symbolIcon("delete_outline")).toBeUndefined()
    expect(symbolIcon("img:/icons/source.svg")).toBeUndefined()
    expect(symbolIcon("sym_o_add")).toBeUndefined()
  })
})
