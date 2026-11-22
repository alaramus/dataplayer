import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"

import type { PairsBlock } from "@/client"
import { copyText } from "@/shared/clipboard"

import ViewBlock from "./ViewBlock.vue"
import { SAMPLE_VIEW } from "./sample"
import type { SectionChild, ViewBlock as Block, ViewValue } from "./view"

vi.mock("@/shared/clipboard", () => ({ copyText: vi.fn().mockResolvedValue(undefined) }))

function draw(block: Block | SectionChild) {
  return mount(ViewBlock, { props: { block }, global: { plugins: [Quasar] } })
}

function field(value: ViewValue) {
  return draw({ kind: "fields", fields: [{ label: "Label", value }] })
}

function section(title: string): Block {
  const found = SAMPLE_VIEW.blocks.find((block) => block.kind === "section" && block.title === title)
  if (found === undefined) throw new Error(title)
  return found
}

describe("the blocks of a document's view (D420)", () => {
  it("draws a section open with its children, and a collapsed one shut", () => {
    const open = draw(section("Overview"))
    const details = open.get('[data-testid="view-section"]')
    expect(details.attributes("open")).toBeDefined()
    expect(details.get("summary").text()).toBe("Overview")
    expect(open.find('[data-testid="view-fields"]').exists()).toBe(true)

    const shut = draw(section("Labels"))
    expect(shut.get('[data-testid="view-section"]').attributes("open")).toBeUndefined()
  })

  it("draws fields as labels beside their values", () => {
    const wrapper = draw(section("Overview"))
    const labels = wrapper.findAll("dt").map((one) => one.text())
    expect(labels).toContain("Memory limit")
    expect(labels).toContain("User")
  })

  it("draws a table with its columns and says how many rows it left out", () => {
    const wrapper = draw(section("Network"))
    const table = wrapper.get('[data-testid="view-table"]')
    expect(table.findAll("th").map((one) => one.text())).toEqual(["Container port", "Host address", "Host port"])
    expect(table.findAll("tbody tr")).toHaveLength(2)
    expect(table.text()).toContain("2 more are in the JSON")
  })

  it("keeps an empty table's columns and says it has none", () => {
    const wrapper = draw({ kind: "table", columns: ["Port", "Host"], rows: [] })
    expect(wrapper.findAll("th").map((one) => one.text())).toEqual(["Port", "Host"])
    expect(wrapper.get("tbody").text()).toBe("None")
  })

  it("draws a notice in the tone its source gave it", () => {
    const bad = draw({ kind: "notice", text: "Killed", tone: "bad" })
    expect(bad.get('[data-testid="view-notice"]').classes()).toContain("dp-tone-wash-error")
    const neutral = draw({ kind: "notice", text: "Note", tone: "neutral" })
    expect(neutral.get('[data-testid="view-notice"]').classes()).toContain("dp-tone-wash-info")
  })

  it("hands a link up rather than following it", async () => {
    const wrapper = field({ kind: "link", text: "shop", node_id: "project:shop" })
    await wrapper.get('[data-testid="view-link"]').trigger("click")
    expect(wrapper.emitted("open")).toEqual([["project:shop", "shop"]])
  })
})

describe("the values of a view (D420)", () => {
  it.each<[string, ViewValue, string]>([
    ["text", { kind: "text", text: "plain words" }, "plain words"],
    ["code", { kind: "code", text: "sh -c 'sleep 1'" }, "sh -c 'sleep 1'"],
    ["number with a unit", { kind: "number", value: 0.5, unit: "CPUs" }, "0.5 CPUs"],
    ["bytes", { kind: "bytes", value: 67_108_864 }, "64.0 MB"],
    ["duration", { kind: "duration", seconds: 7200 }, "2h"],
    ["boolean", { kind: "boolean", value: true }, "Yes"],
    ["state", { kind: "state", word: "healthy", tone: "good" }, "healthy"],
    ["empty", { kind: "empty" }, "—"],
  ])("draws %s", (_, value, shown) => {
    expect(field(value).get("dd").text()).toContain(shown)
  })

  it("draws a moment as its date and how long ago", () => {
    const at = new Date(Date.now() - 3 * 3600 * 1000).toISOString()
    const value = field({ kind: "moment", value: at }).get("dd")
    expect(value.get("time").attributes("datetime")).toBe(at)
    expect(value.text()).toContain("3h ago")
  })

  it("draws a list as chips", () => {
    const value = field({ kind: "list", items: ["latest", "1.27"] }).get("dd")
    expect(value.findAll(".view-value__chip").map((one) => one.text())).toEqual(["latest", "1.27"])
  })

  it("turns a state's tone into the theme's colour, and a neutral one into none", () => {
    const good = field({ kind: "state", word: "running", tone: "good" }).get(".app-state-tag")
    expect(good.classes()).toContain("dp-tone-text-success")
    const neutral = field({ kind: "state", word: "stopped", tone: "neutral" }).get(".app-state-tag")
    expect(neutral.classes()).toContain("app-state-tag--neutral")
  })

  it("copies code with its button", async () => {
    const wrapper = field({ kind: "code", text: "4f1c2a9d" })
    await wrapper.get("button").trigger("click")
    expect(copyText).toHaveBeenCalledWith("4f1c2a9d")
  })
})

describe("pairs, and a value hidden until asked for (D421)", () => {
  const pairs: PairsBlock & { kind: "pairs" } = {
    kind: "pairs",
    pairs: [
      { name: "DB_PASSWORD", value: "hunter2", sensitive: true },
      { name: "LOG_LEVEL", value: "info" },
    ],
  }

  it("draws a sensitive value as dots, and shows it on its button", async () => {
    const wrapper = draw(pairs)
    expect(wrapper.text()).not.toContain("hunter2")
    expect(wrapper.text()).toContain("info")
    expect(wrapper.find('[data-testid="view-pair-hidden"]').exists()).toBe(true)
    await wrapper.get('[data-testid="view-pair-reveal"]').trigger("click")
    expect(wrapper.text()).toContain("hunter2")
    await wrapper.get('[data-testid="view-pair-reveal"]').trigger("click")
    expect(wrapper.text()).not.toContain("hunter2")
  })

  it("does not copy a hidden value", async () => {
    vi.mocked(copyText).mockClear()
    const wrapper = draw(pairs)
    const [secretRow] = wrapper.findAll('[data-testid="view-pair"]')
    const copy = secretRow!.findAll("button").at(-1)!
    expect(copy.attributes("disabled")).toBeDefined()
    await copy.trigger("click")
    expect(copyText).not.toHaveBeenCalled()
  })

  it("offers a filter only past twenty pairs", () => {
    expect(draw(pairs).find('[data-testid="view-pairs-filter"]').exists()).toBe(false)
    const many: PairsBlock & { kind: "pairs" } = {
      kind: "pairs",
      pairs: Array.from({ length: 21 }, (_, index) => ({ name: `VAR_${index}`, value: String(index) })),
    }
    expect(draw(many).find('[data-testid="view-pairs-filter"]').exists()).toBe(true)
  })
})
