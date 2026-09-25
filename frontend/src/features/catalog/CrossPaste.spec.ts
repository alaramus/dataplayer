import { flushPromises, mount } from "@vue/test-utils"
import { AxiosError } from "axios"
import { defineComponent } from "vue"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { PasteOffer } from "@/client"
import CrossPaste from "./CrossPaste.vue"
import { clipboard, forgetClipboard, holdNodes } from "./clipboard"
import type { CrossPasteIntent } from "./pasteOffers"

const pasteCall = vi.hoisted(() => vi.fn())
const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))

vi.mock("@/client", () => ({
  ConnectorsService: { paste: pasteCall },
}))
vi.mock("@/shared/ui", () => ({
  AppButton: defineComponent({ props: ["label"], template: "<button>{{ label }}</button>" }),
  AppForm: defineComponent({ template: "<form><slot /></form>" }),
  AppInput: defineComponent({
    props: ["modelValue", "label", "hint", "error"],
    emits: ["update:modelValue"],
    template:
      "<label><input :value='modelValue' @input=\"$emit('update:modelValue', $event.target.value)\" />" +
      "<span class='hint'>{{ hint }}</span><span class='error'>{{ error }}</span></label>",
  }),
  useToast: () => toasts,
}))
vi.mock("@/shared/windows", () => ({
  WindowDialog: defineComponent({
    name: "WindowDialog",
    props: ["modelValue", "title", "subtitle"],
    template: "<section><h1>{{ title }}</h1><p class='subtitle'>{{ subtitle }}</p><slot /><slot name='actions' /></section>",
  }),
}))

const copying: PasteOffer = { kind: "file_copy", title: "Copy files", available: true }
const saving: PasteOffer = {
  kind: "relation_csv",
  title: "Save as CSV",
  available: true,
  converts: true,
  suggested_name: "people.csv",
}

function intent(offer: PasteOffer, mode: "copy" | "move" = "copy"): CrossPasteIntent {
  return {
    sourceConnectorId: "source",
    sourceNodeIds: ["report.csv"],
    sourceLabel: "report.csv",
    mode,
    destinationConnectorId: "destination",
    destinationNodeId: "incoming",
    destinationLabel: "incoming",
    offer,
  }
}

function conflictRefusal() {
  return new AxiosError("refused", undefined, undefined, undefined, {
    status: 409,
    data: { detail: { message: "people.csv is already there", reason: "conflict" } },
  } as never)
}

function sent() {
  return pasteCall.mock.calls.map((call) => (call[0] as { body: Record<string, unknown> }).body)
}

afterEach(() => {
  pasteCall.mockReset()
  toasts.success.mockReset()
  toasts.error.mockReset()
  forgetClipboard()
})

describe("a paste from another connection", () => {
  it("runs a plain copy at once and reports it through the catalog's reload", async () => {
    pasteCall.mockResolvedValue({
      data: { kind: "file_copy", message: "1 file copied", written: 1, reload_node_ids: ["incoming"] },
    })
    const wrapper = mount(CrossPaste, { props: { intent: intent(copying) } })
    await flushPromises()

    expect(sent()).toEqual([{
      source_connector_id: "source",
      source_node_ids: ["report.csv"],
      destination_node_id: "incoming",
      mode: "copy",
      kind: "file_copy",
      conflict: "refuse",
    }])
    expect(wrapper.emitted("done")?.[0]?.[0]).toMatchObject({
      done: [{ message: "1 file copied", reload_node_ids: ["incoming"] }],
    })
    expect(toasts.success).toHaveBeenCalledWith("1 file copied")
    expect(wrapper.emitted("close")).toHaveLength(1)
    expect(wrapper.findComponent({ name: "WindowDialog" }).exists()).toBe(false)
  })

  it("asks about a taken name before sending anything", async () => {
    const wrapper = mount(CrossPaste, {
      props: { intent: intent({ ...copying, available: false, name_conflict: true, reason: "report.csv is already there" }) },
    })
    await flushPromises()
    expect(pasteCall).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain("report.csv is already there")

    pasteCall.mockResolvedValue({
      data: { kind: "file_copy", message: "1 file copied", written: 1, reload_node_ids: ["incoming"] },
    })
    await wrapper.find('[data-testid="cross-paste-keep-both"]').trigger("click")
    await flushPromises()

    expect(sent()[0]).toMatchObject({ conflict: "rename" })
  })

  it("offers Keep both without Replace when the kind withholds it", async () => {
    const wrapper = mount(CrossPaste, {
      props: {
        intent: intent({ ...copying, kind: "file_move", available: false, name_conflict: true, can_replace: false }, "move"),
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="cross-paste-keep-both"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cross-paste-replace"]').exists()).toBe(false)
  })

  it("refreshes the source and lets the clipboard go after a move", async () => {
    holdNodes("source", ["report.csv"], "move")
    pasteCall.mockResolvedValue({
      data: { kind: "file_move", message: "1 file moved", written: 1, reload_node_ids: ["incoming"] },
    })
    const wrapper = mount(CrossPaste, {
      props: { intent: intent({ ...copying, kind: "file_move", changes_source: true }, "move") },
    })
    await flushPromises()

    expect(wrapper.emitted("sourceChanged")?.[0]).toEqual(["source"])
    expect(clipboard.value).toBeNull()
  })

  it("keeps a clipboard that has moved on since the paste began", async () => {
    holdNodes("source", ["other.csv"], "move")
    pasteCall.mockResolvedValue({
      data: { kind: "file_move", message: "1 file moved", written: 1, reload_node_ids: ["incoming"] },
    })
    mount(CrossPaste, {
      props: { intent: intent({ ...copying, kind: "file_move", changes_source: true }, "move") },
    })
    await flushPromises()

    expect(clipboard.value?.nodeIds).toEqual(["other.csv"])
  })

  it("refreshes the source of a move that failed partway", async () => {
    pasteCall.mockRejectedValue(new AxiosError("failed", undefined, undefined, undefined, {
      status: 422,
      data: { detail: { message: "notes.txt was copied, but its source could not be removed" } },
    } as never))
    const wrapper = mount(CrossPaste, {
      props: { intent: intent({ ...copying, kind: "file_move", changes_source: true }, "move") },
    })
    await flushPromises()

    expect(wrapper.emitted("sourceChanged")?.[0]).toEqual(["source"])
    expect(toasts.error).toHaveBeenCalledWith("notes.txt was copied, but its source could not be removed")
    expect(wrapper.emitted("close")).toHaveLength(1)
  })

  it("asks for a name before converting, then sends the one typed", async () => {
    const wrapper = mount(CrossPaste, { props: { intent: intent(saving) } })
    await flushPromises()
    expect(pasteCall).not.toHaveBeenCalled()
    expect(wrapper.find("h1").text()).toBe("Save as CSV")
    expect((wrapper.find("input").element as HTMLInputElement).value).toBe("people.csv")

    pasteCall.mockResolvedValue({
      data: {
        kind: "relation_csv",
        message: "friends.csv saved with 3 rows",
        written: 1,
        rows: 3,
        name: "friends.csv",
        reload_node_ids: ["incoming"],
      },
    })
    await wrapper.find("input").setValue(" friends.csv ")
    await wrapper.find('[data-testid="cross-paste-save"]').trigger("click")
    await flushPromises()

    expect(sent()).toEqual([expect.objectContaining({
      kind: "relation_csv",
      conflict: "refuse",
      name: "friends.csv",
    })])
    expect(toasts.success).toHaveBeenCalledWith("friends.csv saved with 3 rows")
    expect(wrapper.emitted("close")).toHaveLength(1)
  })

  it("warns that the suggested name is taken before Save is pressed", async () => {
    const wrapper = mount(CrossPaste, { props: { intent: intent({ ...saving, name_conflict: true }) } })
    await flushPromises()

    expect(wrapper.find(".hint").text()).toBe("A file with this name is already here")
    await wrapper.find("input").setValue("another.csv")
    expect(wrapper.find(".hint").text()).toBe("")
  })

  it("moves from the name to the conflict window, keeping the name typed", async () => {
    pasteCall.mockRejectedValueOnce(conflictRefusal())
    const wrapper = mount(CrossPaste, { props: { intent: intent(saving) } })
    await flushPromises()
    await wrapper.find("input").setValue("people.csv")
    await wrapper.find('[data-testid="cross-paste-save"]').trigger("click")
    await flushPromises()

    expect(wrapper.text()).toContain("people.csv is already there")
    pasteCall.mockResolvedValue({
      data: { kind: "relation_csv", message: "people.csv saved with 3 rows", written: 1, reload_node_ids: ["incoming"] },
    })
    await wrapper.find('[data-testid="cross-paste-replace"]').trigger("click")
    await flushPromises()

    expect(sent()[1]).toMatchObject({ conflict: "replace", name: "people.csv" })
  })

  it("keeps the name window open with the reason a name was refused", async () => {
    pasteCall.mockRejectedValue(new AxiosError("refused", undefined, undefined, undefined, {
      status: 422,
      data: { detail: { message: "A name must be a single plain name, without separators" } },
    } as never))
    const wrapper = mount(CrossPaste, { props: { intent: intent(saving) } })
    await flushPromises()
    await wrapper.find("input").setValue("../people")
    await wrapper.find('[data-testid="cross-paste-save"]').trigger("click")
    await flushPromises()

    expect(wrapper.find(".error").text()).toBe("A name must be a single plain name, without separators")
    expect(wrapper.emitted("close")).toBeUndefined()
  })
})
