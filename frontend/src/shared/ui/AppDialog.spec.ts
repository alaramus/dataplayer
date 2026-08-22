import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { afterEach, describe, expect, it } from "vitest"

import AppDialog from "./AppDialog.vue"
import { panelStyle } from "./tokens"

async function openDialog(props: Record<string, unknown> = {}, slots = {}) {
  const wrapper = mount(AppDialog, {
    global: { plugins: [Quasar] },
    props: { modelValue: true, title: "Edit connection", ...props },
    attrs: { "data-testid": "the-dialog" },
    slots,
  })
  await flushPromises()
  return wrapper
}

function card(): HTMLElement {
  const element = document.body.querySelector<HTMLElement>("[data-testid='the-dialog']")
  if (!element) throw new Error("the dialog card was not rendered")
  return element
}

afterEach(() => {
  document.body.innerHTML = ""
})

describe("AppDialog", () => {
  // QDialog renders through a teleport, so an attribute left on it would reach
  // no element a test could address. It has to land on the card.
  it("puts the test id on the card rather than on the dialog", async () => {
    await openDialog()

    expect(card().classList.contains("q-card")).toBe(true)
  })

  it("sizes the card from the named size, not from an inline value", async () => {
    await openDialog({ size: "lg" })

    expect(card().style.width).toBe(panelStyle("lg").width)
  })

  it("shows the title and the subtitle it was given", async () => {
    await openDialog({ subtitle: "postgres-local" })

    expect(card().textContent).toContain("Edit connection")
    expect(card().textContent).toContain("postgres-local")
  })

  it("renders no footer when the caller offers no actions", async () => {
    await openDialog()

    expect(card().querySelector(".q-card__actions")).toBeNull()
  })

  it("renders a footer when the caller fills the actions slot", async () => {
    await openDialog({}, { actions: "<button>Close</button>" })

    expect(card().querySelector(".q-card__actions")).not.toBeNull()
  })
})
