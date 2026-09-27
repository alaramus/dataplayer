/* eslint-disable vue/one-component-per-file -- stand-ins for the kit, a window and two dialogs, not components of the application. */
import { flushPromises, mount } from "@vue/test-utils"
import { AxiosError } from "axios"
import { defineComponent } from "vue"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { PasteOffer } from "@/client"
import { startedHere, toldInThisTab } from "@/features/activity/transfers"
import CrossPaste from "./CrossPaste.vue"
import { clipboard, forgetClipboard, holdNodes } from "./clipboard"
import type { CrossPasteIntent } from "./pasteOffers"

const pasteCall = vi.hoisted(() => vi.fn())
const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))

vi.mock("@/client", () => ({
  ConnectorsService: { paste: pasteCall },
}))
vi.mock("@/shared/ui", () => ({
  AppButton: defineComponent({ props: { label: { type: String, default: "" } }, template: "<button>{{ label }}</button>" }),
  AppForm: defineComponent({ template: "<form><slot /></form>" }),
  AppInput: defineComponent({
    props: {
      modelValue: { type: String, default: "" },
      label: { type: String, default: "" },
      hint: { type: String, default: "" },
      error: { type: String, default: "" },
    },
    emits: ["update:modelValue"],
    template:
      "<label><input :value='modelValue' @input=\"$emit('update:modelValue', $event.target.value)\" />" +
      "<span class='hint'>{{ hint }}</span><span class='error'>{{ error }}</span></label>",
  }),
  useToast: () => toasts,
}))
vi.mock("@/features/grid/CreateTableDialog.vue", () => ({
  default: defineComponent({
    name: "CreateTableDialog",
    props: {
      modelValue: Boolean,
      sourceTitle: { type: String, default: "" },
      sourceColumns: { type: Array, default: () => [] },
      fixedDestination: { type: Object, default: null },
      running: Boolean,
      error: { type: String, default: "" },
    },
    emits: ["update:modelValue", "run"],
    beforeUnmount() {
      this.$emit("update:modelValue", false)
    },
    template: "<div />",
  }),
}))
vi.mock("@/features/grid/ImportDialog.vue", () => ({
  default: defineComponent({
    name: "ImportDialog",
    props: {
      modelValue: Boolean,
      connectorId: { type: String, default: "" },
      nodeId: { type: String, default: "" },
      targetColumns: { type: Array, default: () => [] },
      targetLabel: { type: String, default: "" },
      source: { type: Object, default: null },
      running: Boolean,
      error: { type: String, default: "" },
    },
    emits: ["update:modelValue", "run"],
    beforeUnmount() {
      this.$emit("update:modelValue", false)
    },
    template: "<div />",
  }),
}))
vi.mock("@/shared/windows", () => ({
  // Like the real one, it says it was closed when it is taken away.
  WindowDialog: defineComponent({
    name: "WindowDialog",
    props: { modelValue: Boolean, title: { type: String, default: "" }, subtitle: { type: String, default: "" } },
    emits: ["update:modelValue"],
    beforeUnmount() {
      this.$emit("update:modelValue", false)
    },
    template: "<section><h1>{{ title }}</h1><p class='subtitle'>{{ subtitle }}</p><slot /><slot name='actions' /></section>",
  }),
}))

const copying: PasteOffer = { kind: "file_copy", title: "Copy files", available: true }
const saving: PasteOffer = {
  kind: "relation_csv",
  title: "Save as CSV",
  available: true,
  converts: true,
  workflow: "file-name",
  suggested_name: "people.csv",
}
const columns = [
  { name: "id", type: { sql: "text", category: "string" as const }, insertable: true },
  { name: "name", type: { sql: "text", category: "string" as const }, insertable: true },
]
const creating: PasteOffer = {
  kind: "rows_new_relation",
  title: "Create a table",
  available: true,
  converts: true,
  workflow: "new-relation",
  source_columns: columns,
}
const adding: PasteOffer = {
  kind: "rows_into_relation",
  title: "Add rows to a table",
  available: true,
  converts: true,
  workflow: "into-relation",
  source_columns: columns,
  target_columns: columns,
}

function intent(
  offer: PasteOffer | PasteOffer[],
  mode: "copy" | "move" = "copy"
): CrossPasteIntent {
  return {
    sourceConnectorId: "source",
    sourceNodeIds: ["report.csv"],
    sourceLabel: "report.csv",
    mode,
    destinationConnectorId: "destination",
    destinationNodeId: "incoming",
    destinationLabel: "incoming",
    targetNodeId: null,
    targetLabel: "",
    offers: Array.isArray(offer) ? offer : [offer],
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
      target_node_id: null,
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

  it("hands a transfer started as a job to the footer and closes at once", async () => {
    holdNodes("source", ["report.csv"], "move")
    pasteCall.mockResolvedValue({ data: { outcome: "started", job: { id: "job-7" } } })
    const wrapper = mount(CrossPaste, {
      props: { intent: intent({ ...copying, kind: "file_move", changes_source: true }, "move") },
    })
    await flushPromises()

    expect(wrapper.emitted("close")).toHaveLength(1)
    // Nothing has arrived yet, so nothing is announced or re-read here; what
    // was ticked for it is let go all the same.
    expect(wrapper.emitted("done")).toBeUndefined()
    expect(wrapper.emitted("started")).toHaveLength(1)
    expect(toasts.success).not.toHaveBeenCalled()
    // A Cut is spent the moment its move starts.
    expect(clipboard.value).toBeNull()
    expect(startedHere.value.has("job-7")).toBe(true)
    toldInThisTab("job-7")
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
    expect(wrapper.emitted("close")).toBeUndefined()
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

  it("lists several offers, and goes on with the one chosen", async () => {
    const wrapper = mount(CrossPaste, {
      props: {
        intent: {
          ...intent([creating, adding]),
          destinationLabel: "public",
          targetNodeId: "public.orders",
          targetLabel: "orders",
        },
      },
    })
    await flushPromises()
    expect(pasteCall).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="cross-paste-offer-rows_new_relation"]').text())
      .toBe("Create a table: public")
    expect(wrapper.find('[data-testid="cross-paste-offer-rows_into_relation"]').text())
      .toBe("Add rows to a table: orders")

    await wrapper.find('[data-testid="cross-paste-offer-rows_into_relation"]').trigger("click")

    const form = wrapper.findComponent({ name: "ImportDialog" })
    expect(form.props("nodeId")).toBe("public.orders")
    expect(form.props("source")).toEqual({
      connectorId: "source",
      nodeId: "report.csv",
      label: "report.csv",
      columns,
    })
    expect(wrapper.findComponent({ name: "CreateTableDialog" }).exists()).toBe(false)
    // Taking the list away is moving on, not cancelling.
    expect(wrapper.emitted("close")).toBeUndefined()
  })

  it("creates a table in the place Paste was chosen in, with the columns chosen", async () => {
    pasteCall.mockResolvedValue({
      data: { kind: "rows_new_relation", message: "people created with 2 rows", written: 1, reload_node_ids: ["incoming"] },
    })
    const wrapper = mount(CrossPaste, { props: { intent: intent(creating) } })
    await flushPromises()
    const form = wrapper.findComponent({ name: "CreateTableDialog" })
    expect(form.props("fixedDestination")).toEqual({
      connectorId: "destination",
      parentNodeId: "incoming",
      label: "incoming",
    })
    expect(form.props("sourceColumns")).toEqual(columns)

    form.vm.$emit("run", {
      connectorId: "destination",
      parentNodeId: "incoming",
      name: "people",
      columns: [{ source: "id", target: "id", type_code: "text" }],
    })
    await flushPromises()

    expect(sent()[0]).toMatchObject({
      kind: "rows_new_relation",
      name: "people",
      columns: [{ source: "id", target: "id", type_code: "text" }],
    })
    expect(toasts.success).toHaveBeenCalledWith("people created with 2 rows")
    expect(wrapper.emitted("close")).toHaveLength(1)
  })

  it("keeps the form open with the reason a value could not cross", async () => {
    pasteCall.mockRejectedValue(new AxiosError("refused", undefined, undefined, undefined, {
      status: 422,
      data: { detail: { message: "'nine' cannot be read by id (row 2)" } },
    } as never))
    const wrapper = mount(CrossPaste, {
      props: { intent: { ...intent(adding), targetNodeId: "public.orders", targetLabel: "orders" } },
    })
    await flushPromises()
    const form = wrapper.findComponent({ name: "ImportDialog" })

    form.vm.$emit("run", {
      connectorId: "source",
      nodeId: "report.csv",
      columns: [{ source: "id", target: "id" }],
    })
    await flushPromises()

    expect(sent()[0]).toMatchObject({
      kind: "rows_into_relation",
      target_node_id: "public.orders",
      columns: [{ source: "id", target: "id" }],
    })
    expect(sent()[0]).not.toHaveProperty("name")
    expect(form.props("error")).toBe("'nine' cannot be read by id (row 2)")
    expect(wrapper.emitted("close")).toBeUndefined()
  })
})
