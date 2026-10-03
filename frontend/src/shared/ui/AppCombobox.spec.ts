import { flushPromises, mount } from "@vue/test-utils"
import type { DOMWrapper } from "@vue/test-utils"
import { Quasar } from "quasar"
import { afterEach, describe, expect, it } from "vitest"
import { ref } from "vue"

import AppCombobox from "./AppCombobox.vue"
import type { SelectOption } from "./AppSelect.vue"

/** The field, as `get` hands it back. */
type Field = Omit<DOMWrapper<HTMLInputElement>, "exists">

const OPTIONS: SelectOption[] = [
  { label: "Search in local pg", value: "scope", offer: true },
  { label: "Connections", value: "h1", group: true },
  { label: "local pg", value: "c1", description: "PostgreSQL" },
  { label: "Guide", value: "h2", group: true },
  { label: "Connections", value: "g1", descriptionRuns: [{ text: "orders", hit: true }] },
]

async function mountBox(props: Record<string, unknown> = {}) {
  const words = ref("")
  const open = ref(false)
  const wrapper = mount(AppCombobox, {
    attachTo: document.body,
    global: { plugins: [Quasar] },
    props: {
      modelValue: words.value,
      "onUpdate:modelValue": (value: string) => {
        words.value = value
        void wrapper.setProps({ modelValue: value })
      },
      open: open.value,
      "onUpdate:open": (value: boolean) => {
        open.value = value
        void wrapper.setProps({ open: value })
      },
      label: "Search",
      options: OPTIONS,
      submitLabel: "Show all results",
      ...props,
    },
  })
  await flushPromises()
  const input = wrapper.get<HTMLInputElement>('input[role="combobox"]')
  return { wrapper, input, words, open }
}

async function press(input: Field, key: string) {
  await input.trigger("keydown", { key })
  await flushPromises()
}

async function type(input: Field, text: string) {
  input.element.value = text
  input.element.setSelectionRange(text.length, text.length)
  await input.trigger("input")
  await flushPromises()
}

function activeOption(input: Field) {
  const id = input.attributes("aria-activedescendant")
  return id === undefined ? null : document.getElementById(id)
}

afterEach(() => {
  document.body.innerHTML = ""
})

describe("AppCombobox", () => {
  it("is a combobox over a listbox, closed and with nothing active at first", async () => {
    const { input } = await mountBox()
    expect(input.attributes("aria-expanded")).toBe("false")
    expect(input.attributes("aria-activedescendant")).toBeUndefined()
    expect(document.getElementById(input.attributes("aria-controls") ?? "")).toBeNull()
  })

  it("opens on typing with no row active, so Enter submits the words", async () => {
    const { wrapper, input } = await mountBox()
    await type(input, "orders")
    expect(input.attributes("aria-expanded")).toBe("true")
    expect(document.querySelector('[role="listbox"]')).not.toBeNull()
    expect(input.attributes("aria-activedescendant")).toBeUndefined()
    await press(input, "Enter")
    expect(wrapper.emitted("submit")).toHaveLength(1)
    expect(wrapper.emitted("pick")).toBeUndefined()
  })

  it("walks the rows with the arrows, past the headings, and Enter takes the active one", async () => {
    const { wrapper, input } = await mountBox()
    await type(input, "pg")
    await press(input, "ArrowDown")
    expect(activeOption(input)?.textContent).toContain("Search in local pg")
    await press(input, "ArrowDown")
    const row = activeOption(input)
    expect(row?.getAttribute("role")).toBe("option")
    expect(row?.getAttribute("aria-selected")).toBe("true")
    expect(row?.textContent).toContain("local pg")
    await press(input, "Enter")
    expect(wrapper.emitted("pick")).toEqual([["c1"]])
  })

  it("goes up from nothing to the last row, which asks for everything", async () => {
    const { wrapper, input } = await mountBox()
    await type(input, "pg")
    await press(input, "ArrowUp")
    expect(activeOption(input)?.textContent).toContain("Show all results")
    await press(input, "Enter")
    expect(wrapper.emitted("submit")).toHaveLength(1)
  })

  it("groups the rows under their headings for a reader", async () => {
    const { input } = await mountBox()
    await type(input, "pg")
    const groups = [...document.querySelectorAll('[role="group"][aria-labelledby]')]
    expect(groups.map((group) => document.getElementById(group.getAttribute("aria-labelledby") ?? "")?.textContent?.trim()))
      .toEqual(["Connections", "Guide"])
  })

  it("closes the list on the first Escape and keeps the words, and leaves on the second", async () => {
    const { wrapper, input, words } = await mountBox()
    await type(input, "orders")
    await press(input, "ArrowDown")
    await press(input, "Escape")
    expect(input.attributes("aria-expanded")).toBe("false")
    expect(input.attributes("aria-activedescendant")).toBeUndefined()
    expect(words.value).toBe("orders")
    expect(wrapper.emitted("leave")).toBeUndefined()
    await press(input, "Escape")
    expect(wrapper.emitted("leave")).toHaveLength(1)
  })

  it("leaves on the first Escape when there is no list to close", async () => {
    const { wrapper, input } = await mountBox({ options: [], submitLabel: undefined })
    await input.trigger("click")
    await flushPromises()
    expect(input.attributes("aria-expanded")).toBe("false")
    await press(input, "Escape")
    expect(wrapper.emitted("leave")).toHaveLength(1)
  })

  it("keeps the row an arrow stood on when the list is drawn again around it", async () => {
    const { wrapper, input } = await mountBox()
    await type(input, "pg")
    await press(input, "ArrowDown")
    await press(input, "ArrowDown")
    expect(activeOption(input)?.textContent).toContain("local pg")
    // A late answer adds a row above: the same row stays active, by its value.
    await wrapper.setProps({
      options: [...OPTIONS.slice(0, 2), { label: "new pg", value: "c0" }, ...OPTIONS.slice(2)],
    })
    await flushPromises()
    expect(activeOption(input)?.textContent).toContain("local pg")
    // And once its row is gone, nothing is active rather than its neighbour.
    await wrapper.setProps({ options: OPTIONS.filter((option) => option.value !== "c1") })
    await flushPromises()
    expect(input.attributes("aria-activedescendant")).toBeUndefined()
  })

  it("keeps the last row under the others, outside what scrolls", async () => {
    const { input } = await mountBox({ maxHeight: "120px" })
    await type(input, "pg")
    const scroller = document.querySelector<HTMLElement>(".app-combobox__rows")
    expect(scroller?.style.maxHeight).toBe("120px")
    const last = [...document.querySelectorAll('[role="option"]')].at(-1)
    expect(last?.textContent).toContain("Show all results")
    expect(scroller?.contains(last ?? null)).toBe(false)
  })

  it("takes an offer with the right arrow from the end of the words, and only from there", async () => {
    const { wrapper, input } = await mountBox()
    await type(input, "orders")
    input.element.setSelectionRange(2, 2)
    await press(input, "ArrowRight")
    expect(wrapper.emitted("pick")).toBeUndefined()
    input.element.setSelectionRange(6, 6)
    await press(input, "ArrowRight")
    expect(wrapper.emitted("pick")).toEqual([["scope"]])
  })

  it("does not take a row that is not an offer with the right arrow", async () => {
    const { wrapper, input } = await mountBox({ options: OPTIONS.slice(1) })
    await type(input, "orders")
    await press(input, "ArrowRight")
    expect(wrapper.emitted("pick")).toBeUndefined()
  })

  it("removes its chip with Backspace before the first word", async () => {
    const { wrapper, input } = await mountBox({ chip: "in local pg" })
    expect(wrapper.get('[data-testid="combobox-chip"]').text()).toBe("in local pg")
    await type(input, "or")
    input.element.setSelectionRange(1, 1)
    await press(input, "Backspace")
    expect(wrapper.emitted("remove-chip")).toBeUndefined()
    input.element.setSelectionRange(0, 0)
    await press(input, "Backspace")
    expect(wrapper.emitted("remove-chip")).toHaveLength(1)
  })

  it("says its status in a polite live region that is always there", async () => {
    const { wrapper } = await mountBox({ status: "Searching 3 places" })
    const live = wrapper.get('[role="status"]')
    expect(live.text()).toBe("Searching 3 places")
    await wrapper.setProps({ status: "2 places did not answer" })
    expect(wrapper.get('[role="status"]').text()).toBe("2 places did not answer")
  })

  it("hands on a row's own action from its button, the row not taken", async () => {
    const { wrapper, input } = await mountBox({
      options: [{ label: "orders", value: "n1", actionIcon: "my_location", actionLabel: "Show in catalog" }],
    })
    await type(input, "ord")
    const button = document.querySelector<HTMLElement>('[role="option"] button')
    expect(button).not.toBeNull()
    button?.click()
    await flushPromises()
    expect(wrapper.emitted("action")).toEqual([["n1"]])
    expect(wrapper.emitted("pick")).toBeUndefined()
  })

  it("takes the active row's action with Ctrl+Enter or ⌘Enter, and the row itself where it has none", async () => {
    const { wrapper, input } = await mountBox({
      options: [
        { label: "orders", value: "n1", actionIcon: "my_location", actionLabel: "Show in catalog" },
        { label: "Guide", value: "g1" },
      ],
    })
    await type(input, "ord")
    await press(input, "ArrowDown")
    await input.trigger("keydown", { key: "Enter", ctrlKey: true })
    await input.trigger("keydown", { key: "Enter", metaKey: true })
    await flushPromises()
    expect(wrapper.emitted("action")).toEqual([["n1"], ["n1"]])
    await press(input, "ArrowDown")
    await input.trigger("keydown", { key: "Enter", ctrlKey: true })
    await flushPromises()
    expect(wrapper.emitted("pick")).toEqual([["g1"]])
  })

  it("drops a row by its cross or by Delete on it, the row not taken and the list kept", async () => {
    const options: SelectOption[] = [
      { label: "Recent searches", value: "group:recent", group: true, removeLabel: "Clear recent searches" },
      { label: "orders", value: "recent:orders", removeLabel: "Remove from recent searches" },
      { label: "users", value: "recent:users", removeLabel: "Remove from recent searches" },
    ]
    const { wrapper, input, open } = await mountBox({ options })
    await type(input, "o")
    document.querySelector<HTMLElement>('[role="option"] button[aria-label="Remove from recent searches"]')?.click()
    await flushPromises()
    expect(wrapper.emitted("remove")).toEqual([["recent:orders"]])

    await press(input, "ArrowDown")
    await press(input, "Delete")
    expect(wrapper.emitted("remove")).toEqual([["recent:orders"], ["recent:orders"]])
    // Gone from the list, the arrows stand on the row that took its place.
    await wrapper.setProps({ options: options.filter((option) => option.value !== "recent:orders") })
    await flushPromises()
    expect(activeOption(input)?.textContent).toContain("users")

    document.querySelector<HTMLElement>('button[aria-label="Clear recent searches"]')?.click()
    await flushPromises()
    expect(wrapper.emitted("remove")?.at(-1)).toEqual(["group:recent"])
    expect(wrapper.emitted("pick")).toBeUndefined()
    expect(open.value).toBe(true)
  })

  it("deletes a character with Delete while no row is active", async () => {
    const { wrapper, input } = await mountBox({
      options: [{ label: "orders", value: "recent:orders", removeLabel: "Remove from recent searches" }],
    })
    await type(input, "o")
    const event = new KeyboardEvent("keydown", { key: "Delete", cancelable: true })
    input.element.dispatchEvent(event)
    await flushPromises()
    expect(event.defaultPrevented).toBe(false)
    expect(wrapper.emitted("remove")).toBeUndefined()
  })

  it("marks the words that matched as text, never as markup", async () => {
    const { input } = await mountBox({
      options: [{ label: "<b>x</b>", value: "x", labelRuns: [{ text: "<b>", hit: true }, { text: "x</b>", hit: false }] }],
    })
    await type(input, "xx")
    const mark = document.querySelector('[role="listbox"] mark')
    expect(mark?.textContent).toBe("<b>")
    expect(document.querySelector('[role="listbox"] b')).toBeNull()
  })
})
