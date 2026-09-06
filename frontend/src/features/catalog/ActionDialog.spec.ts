import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { AxiosError } from "axios"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import type { ActionCommand } from "@/features/catalog/actions"
import { AppToggle } from "@/shared/ui"
import { createOperations, operationsKey } from "@/shared/operations"
import type { Operations } from "@/shared/operations"
import { withWindowHost } from "@/shared/testing/windows"

import ActionDialog from "./ActionDialog.vue"

const DROP: ActionCommand = {
  name: "drop_relation",
  label: "Drop",
  destructive: true,
  question: null,
  takesFile: false,
  takesManyFiles: false,
  previews: true,
  takesSet: false,
  previewsSet: false,
  choices: {},
  defaults: {},
  downloads: false,
  actsOn: "node",
  fields: [
    {
      name: "cascade",
      label: "Also drop everything built on it",
      kind: "boolean",
      required: false,
      defaultValue: false,
      group: "general",
    },
  ],
}

const RENAME: ActionCommand = {
  name: "rename",
  label: "Rename",
  destructive: false,
  question: null,
  takesFile: false,
  takesManyFiles: false,
  previews: false,
  takesSet: false,
  previewsSet: false,
  choices: {},
  defaults: {},
  downloads: false,
  actsOn: "node",
  fields: [
    {
      name: "new_name",
      label: "New name",
      kind: "text",
      required: true,
      purpose: "node-name",
      group: "general",
    },
  ],
}

const MOVE: ActionCommand = {
  name: "move_relation",
  label: "Move to schema",
  destructive: false,
  question: null,
  takesFile: false,
  takesManyFiles: false,
  previews: false,
  takesSet: false,
  previewsSet: false,
  choices: {},
  defaults: {},
  downloads: false,
  actsOn: "node",
  fields: [
    {
      name: "target_schema",
      label: "Target schema",
      kind: "text",
      required: true,
      purpose: "grouping",
      group: "general",
    },
  ],
}

const UPLOAD: ActionCommand = {
  name: "upload",
  label: "Upload files",
  destructive: false,
  question: null,
  takesFile: true,
  takesManyFiles: true,
  previews: false,
  takesSet: false,
  previewsSet: false,
  choices: {},
  defaults: {},
  downloads: false,
  actsOn: "children",
  fields: [
    {
      name: "conflict",
      label: "File conflict",
      kind: "hidden",
      required: false,
      defaultValue: "refuse",
      purpose: "file-conflict",
      group: "general",
    },
  ],
}

function mountDialog(
  command: ActionCommand = DROP,
  nodeIds: (string | null)[] = ["demo.customers"],
  targetNode?: { label: string; kind: string },
  groupings: { id: string; label: string; system: boolean }[] = [],
  operations: Operations = createOperations()
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(
    withWindowHost(ActionDialog, {
      command,
      connectorId: "c-1",
      nodeIds,
      nodeLabel: "customers",
      targetNode,
      groupings,
    }),
    {
      global: {
        provide: { [operationsKey as symbol]: operations },
        plugins: [
          [Quasar, { plugins: { Dialog, Notify } }],
          [VueQueryPlugin, { queryClient }],
        ],
      },
    }
  )
}

/** The dialog waits before asking, so the wait has to pass in the test too. */
async function settle() {
  await vi.advanceTimersByTimeAsync(300)
  await flushPromises()
}

function text(testid: string): string {
  return document.body.querySelector(`[data-testid="${testid}"]`)?.textContent ?? ""
}

function click(testid: string): void {
  document.body.querySelector<HTMLElement>(`[data-testid="${testid}"]`)?.click()
}

/**
 * What the picker hands back once the user has chosen.
 *
 * By name rather than by the component itself: the file field is generic
 * over the shape of its value, and a generic component reaches this call as
 * a functional one, whose wrapper has no instance to emit from.
 */
function choose(
  wrapper: ReturnType<typeof mountDialog>,
  chosen: File[]
): void {
  wrapper
    .findComponent({ name: "AppFileInput" })
    .vm.$emit("update:modelValue", chosen)
}

function csv(name: string): File {
  return new File(["id"], name, { type: "text/csv" })
}

function refused(status: number): AxiosError {
  return new AxiosError("refused", undefined, undefined, undefined, {
    status,
  } as never)
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("what an action would do", () => {
  it("asks a plain destructive question that names the target", async () => {
    const wrapper = mountDialog(DROP, ["demo.customers"], {
      label: "customers",
      kind: "table",
    })
    await flushPromises()

    expect(text("action-confirmation")).toContain(
      "Are you sure you want to delete customers?"
    )
    expect(document.body.querySelector('[data-testid="action-warning"]')).toBeNull()
    wrapper.unmount()
  })

  it("asks the question the action wrote, when it wrote one", async () => {
    // Every destructive action there was removed what it named, so the dialog
    // wrote "are you sure you want to delete this" itself. Setting an expiry
    // is destructive and is not a deletion, and only the action knows that.
    const wrapper = mountDialog(
      {
        ...DROP,
        name: "set_expiry",
        label: "Set expiry",
        question: "This key will be removed when the time is up. Set the expiry?",
        previews: false,
        fields: [],
      },
      ["k:session"]
    )
    await flushPromises()

    expect(text("action-confirmation")).toContain("when the time is up")
    expect(text("action-confirmation")).not.toContain("want to delete")
    wrapper.unmount()
  })

  it("asks the source, and shows what it said in its own words", async () => {
    const preview = vi.spyOn(ConnectorsService, "previewAction").mockResolvedValue({
      data: {
        summary: "Something else is built on this relation",
        items: ["view demo.rich_customers depends on table demo.customers"],
        blocked: true,
      },
    } as never)
    const wrapper = mountDialog()
    await settle()

    expect(preview).toHaveBeenCalledWith({
      path: { connector_id: "c-1", action_name: "drop_relation" },
      body: { node_id: "demo.customers", params: { cascade: false } },
    })
    expect(text("action-preview")).toContain("rich_customers")
    wrapper.unmount()
  })

  it("turns the button off while the source says it would refuse", async () => {
    vi.spyOn(ConnectorsService, "previewAction").mockResolvedValue({
      data: { summary: "no", items: [], blocked: true },
    } as never)
    const wrapper = mountDialog()
    await settle()

    const submit = document.body.querySelector<HTMLButtonElement>(
      '[data-testid="action-submit"]'
    )
    expect(submit?.disabled).toBe(true)
    wrapper.unmount()
  })

  it("asks again when the form changes, because the answer is about it", async () => {
    const preview = vi.spyOn(ConnectorsService, "previewAction").mockResolvedValue({
      data: { summary: "fine", items: [], blocked: false },
    } as never)
    const wrapper = mountDialog()
    await settle()

    wrapper.findComponent(AppToggle).vm.$emit("update:modelValue", true)
    await settle()

    expect(preview.mock.calls.map(([request]) => request.body.params)).toEqual([
      { cascade: false },
      { cascade: true },
    ])
    wrapper.unmount()
  })

  it("says nothing about an action that cannot be asked", async () => {
    const preview = vi.spyOn(ConnectorsService, "previewAction")
    const wrapper = mountDialog({ ...DROP, previews: false })
    await settle()

    expect(preview).not.toHaveBeenCalled()
    expect(document.body.querySelector('[data-testid="action-preview"]')).toBeNull()
    wrapper.unmount()
  })

  it("does not ask about a form that is applied to several nodes", async () => {
    const preview = vi.spyOn(ConnectorsService, "previewAction")
    const wrapper = mountDialog(DROP, ["a", "b"])
    await settle()

    expect(preview).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it("says it could not find out, and still lets the action be run", async () => {
    vi.spyOn(ConnectorsService, "previewAction").mockRejectedValue(new Error("nope"))
    const wrapper = mountDialog()
    await settle()

    expect(text("action-preview-error")).not.toBe("")
    const submit = document.body.querySelector<HTMLButtonElement>(
      '[data-testid="action-submit"]'
    )
    expect(submit?.disabled).toBe(false)
    wrapper.unmount()
  })
})

describe("renaming a file", () => {
  it("starts with the current name selected without its extension", async () => {
    const wrapper = mountDialog(RENAME, ["reports/uploaded.csv"], {
      label: "uploaded.csv",
      kind: "file",
    })
    await flushPromises()

    const input = document.body.querySelector<HTMLInputElement>(
      '[data-testid="field-new_name"]'
    )
    expect(input?.value).toBe("uploaded")
    wrapper.unmount()
  })

  it("keeps the old extension when no new extension is typed", async () => {
    const run = vi.spyOn(ConnectorsService, "runAction").mockResolvedValue({
      data: { message: "renamed", reload_node_ids: ["reports"] },
    } as never)
    const wrapper = mountDialog(RENAME, ["reports/uploaded.csv"], {
      label: "uploaded.csv",
      kind: "file",
    })
    await flushPromises()

    const input = document.body.querySelector<HTMLInputElement>(
      '[data-testid="field-new_name"]'
    )
    if (input === null) throw new Error("Rename field did not render")
    input.value = "renamed"
    input.dispatchEvent(new Event("input", { bubbles: true }))
    document.body.querySelector<HTMLElement>('[data-testid="action-submit"]')?.click()
    await flushPromises()

    expect(run).toHaveBeenCalledWith({
      path: { connector_id: "c-1", action_name: "rename" },
      body: {
        node_id: "reports/uploaded.csv",
        params: { new_name: "renamed.csv" },
      },
    })
    wrapper.unmount()
  })
})

describe("renaming a database relation", () => {
  it("starts with the current relation name", async () => {
    const wrapper = mountDialog(RENAME, ["demo.customers"], {
      label: "customers",
      kind: "table",
    })
    await flushPromises()

    const input = document.body.querySelector<HTMLInputElement>(
      '[data-testid="field-new_name"]'
    )
    expect(input?.value).toBe("customers")
    wrapper.unmount()
  })
})

describe("uploading files", () => {
  it("keeps unsent files for retry when the queue is paused and stopped", async () => {
    const operations = createOperations()
    let release: () => void = () => { throw new Error("The first upload has not started") }
    const held = new Promise<never>((resolve) => {
      release = () => resolve({ data: { message: "first.csv uploaded", reload_node_ids: [null] } } as never)
    })
    const upload = vi.spyOn(ConnectorsService, "runActionWithFile")
      .mockImplementationOnce((request) => {
        request.onUploadProgress?.({ loaded: 50, total: 100 } as never)
        return held
      })
      .mockResolvedValue({ data: { message: "Uploaded", reload_node_ids: [null] } } as never)
    const wrapper = mountDialog(UPLOAD, [null], undefined, [], operations)
    await flushPromises()
    choose(wrapper, [csv("first.csv"), csv("second.csv"), csv("third.csv")])
    await flushPromises()
    click("action-submit")
    await flushPromises()
    const operation = operations.items.value[0]!
    expect(operation.transfer).toEqual({ loaded: 50, total: 100 })
    operations.pause(operation.id)
    release()
    await flushPromises()
    expect(operations.items.value[0]?.state).toBe("paused")
    expect(upload).toHaveBeenCalledTimes(1)
    operations.stop(operation.id)
    await flushPromises()
    expect(operations.items.value[0]).toMatchObject({ state: "cancelled", completed: 1 })
    expect(text("action-files")).not.toContain("first.csv")
    expect(text("action-files")).toContain("second.csv")
    expect(text("action-files")).toContain("third.csv")
    expect(text("action-error")).toContain("Not started")
    click("action-submit")
    await flushPromises()
    expect(upload.mock.calls.map(([request]) => {
      const file = request.body.file
      return file instanceof File ? file.name : null
    })).toEqual([
      "first.csv", "second.csv", "third.csv",
    ])
    wrapper.unmount()
  })

  it("continues to report an upload after its form closes", async () => {
    const operations = createOperations()
    let release: () => void = () => { throw new Error("The upload has not started") }
    vi.spyOn(ConnectorsService, "runActionWithFile").mockReturnValue(new Promise<never>((resolve) => {
      release = () => resolve({ data: { message: "Uploaded", reload_node_ids: [null] } } as never)
    }))
    const wrapper = mountDialog(UPLOAD, [null], undefined, [], operations)
    await flushPromises()
    choose(wrapper, [csv("first.csv")])
    await flushPromises()
    click("action-submit")
    await flushPromises()
    wrapper.unmount()
    expect(operations.items.value[0]?.state).toBe("running")
    release()
    await flushPromises()
    expect(operations.items.value[0]?.state).toBe("succeeded")
  })

  it("stages what was chosen and sends nothing until it is asked to", async () => {
    // The whole reason the list exists: a picker that uploaded on its own
    // would leave nothing to correct.
    const upload = vi.spyOn(ConnectorsService, "runActionWithFile")
    const wrapper = mountDialog(UPLOAD, [null])
    await flushPromises()

    choose(wrapper, [csv("first.csv"), csv("second.csv")])
    await flushPromises()

    expect(upload).not.toHaveBeenCalled()
    expect(text("action-files")).toContain("first.csv")
    expect(text("action-files")).toContain("second.csv")
    wrapper.unmount()
  })

  it("does not send a file that was taken off the list", async () => {
    const upload = vi.spyOn(ConnectorsService, "runActionWithFile").mockResolvedValue({
      data: { message: "second.csv uploaded", reload_node_ids: [null] },
    } as never)
    const wrapper = mountDialog(UPLOAD, [null])
    await flushPromises()

    const kept = csv("second.csv")
    choose(wrapper, [csv("first.csv"), kept])
    await flushPromises()
    click("action-file-remove-0")
    await flushPromises()
    click("action-submit")
    await flushPromises()

    expect(upload).toHaveBeenCalledTimes(1)
    expect(upload).toHaveBeenCalledWith({
      onUploadProgress: expect.any(Function),
      path: { connector_id: "c-1", action_name: "upload" },
      body: {
        file: kept,
        node_id: "",
        params: JSON.stringify({ conflict: "refuse" }),
      },
    })
    wrapper.unmount()
  })

  it("sends one request per file, and one refusal does not stop the rest", async () => {
    const upload = vi
      .spyOn(ConnectorsService, "runActionWithFile")
      .mockResolvedValueOnce({
        data: { message: "first.csv uploaded", reload_node_ids: [null] },
      } as never)
      .mockRejectedValueOnce(refused(409))
      .mockResolvedValueOnce({
        data: { message: "second (1).csv uploaded", reload_node_ids: [null] },
      } as never)
    const wrapper = mountDialog(UPLOAD, [null])
    await flushPromises()

    const taken = csv("second.csv")
    choose(wrapper, [csv("first.csv"), taken])
    await flushPromises()
    click("action-submit")
    await flushPromises()

    // What landed is gone from the list; what was refused stays there, which
    // is where the answer to it is.
    expect(upload).toHaveBeenCalledTimes(2)
    expect(text("action-files")).toContain("second.csv")
    expect(text("action-files")).not.toContain("first.csv")
    expect(text("action-error")).toContain("second.csv already exists")

    click("action-keep-both")
    await flushPromises()

    expect(upload).toHaveBeenCalledTimes(3)
    expect(upload).toHaveBeenLastCalledWith({
      onUploadProgress: expect.any(Function),
      path: { connector_id: "c-1", action_name: "upload" },
      body: {
        file: taken,
        node_id: "",
        params: JSON.stringify({ conflict: "rename" }),
      },
    })
    wrapper.unmount()
  })

  it("asks about a conflict only after the file has been chosen", async () => {
    const upload = vi
      .spyOn(ConnectorsService, "runActionWithFile")
      .mockRejectedValueOnce(refused(409))
      .mockResolvedValueOnce({
        data: { message: "report (1).csv uploaded", reload_node_ids: [null] },
      } as never)
    const wrapper = mountDialog(UPLOAD, [null])
    await flushPromises()

    const file = csv("report.csv")
    choose(wrapper, [file])
    await flushPromises()

    // Nothing has been asked yet, so there is nothing to be in conflict with.
    expect(document.body.querySelector('[data-testid="action-keep-both"]')).toBeNull()
    click("action-submit")
    await flushPromises()

    expect(document.body.querySelector('[data-testid="action-keep-both"]')).not.toBeNull()
    click("action-keep-both")
    await flushPromises()

    expect(upload).toHaveBeenLastCalledWith({
      onUploadProgress: expect.any(Function),
      path: { connector_id: "c-1", action_name: "upload" },
      body: {
        file,
        node_id: "",
        params: JSON.stringify({ conflict: "rename" }),
      },
    })
    wrapper.unmount()
  })
})

/**
 * Where a relation goes is picked from what is there.
 *
 * A typed schema name has to match one the server already has, exactly, or the
 * move is refused — which makes typing it a guess with one right answer. The
 * server says the field names a grouping and the level says which groupings
 * there are.
 */
describe("moving a relation", () => {
  const SCHEMAS = [
    { id: "public", label: "public", system: false },
    { id: "pg_catalog", label: "pg_catalog", system: true },
    { id: "reports", label: "reports", system: false },
  ]

  it("offers the schemas of the connection, and not the server's own", async () => {
    const wrapper = mountDialog(MOVE, ["public.customers"], undefined, SCHEMAS)
    await flushPromises()

    const select = wrapper.findComponent({ name: "AppSelect" })
    expect(select.props("options")).toEqual([
      { value: "public", label: "public" },
      { value: "reports", label: "reports" },
    ])
    wrapper.unmount()
  })

  it("sends the schema that was chosen", async () => {
    const run = vi.spyOn(ConnectorsService, "runAction").mockResolvedValue({
      data: { message: "customers moved to reports", reload_node_ids: ["public", "reports"] },
    } as never)
    const wrapper = mountDialog(MOVE, ["public.customers"], undefined, SCHEMAS)
    await flushPromises()

    wrapper
      .findComponent({ name: "AppSelect" })
      .vm.$emit("update:modelValue", "reports")
    await flushPromises()
    click("action-submit")
    await flushPromises()

    expect(run).toHaveBeenCalledWith({
      path: { connector_id: "c-1", action_name: "move_relation" },
      body: { node_id: "public.customers", params: { target_schema: "reports" } },
    })
    wrapper.unmount()
  })

  it("still takes a typed name from a source that offers no groupings", async () => {
    const wrapper = mountDialog(MOVE, ["public.customers"])
    await flushPromises()

    expect(wrapper.findComponent({ name: "AppSelect" }).exists()).toBe(false)
    expect(
      document.body.querySelector('[data-testid="field-target_schema"]')
    ).not.toBeNull()
    wrapper.unmount()
  })
})

describe("an action with nothing to fill in", () => {
  const PASTE: ActionCommand = {
    name: "paste",
    label: "Paste",
    destructive: false,
    question: null,
    takesFile: false,
    takesManyFiles: false,
    previews: false,
    takesSet: false,
    previewsSet: false,
    choices: {},
    defaults: {},
    downloads: false,
    actsOn: "children",
    fields: [
      {
        name: "sources",
        label: "What to put here",
        kind: "hidden",
        required: false,
        defaultValue: [],
        group: "general",
        purpose: "clipboard-nodes",
      },
      {
        name: "mode",
        label: "Copy or move",
        kind: "hidden",
        required: false,
        defaultValue: "copy",
        group: "general",
        purpose: "clipboard-mode",
      },
    ],
  }

  it("runs at once instead of opening an empty confirmation", async () => {
    // Pick up, then put down. A window between the two asks nothing and
    // confirms a gesture already made.
    const run = vi.spyOn(ConnectorsService, "runAction").mockResolvedValue({
      data: { message: "1 file copied", reload_node_ids: ["reports"] },
    } as never)
    const wrapper = mountDialog(PASTE, ["reports"])
    await flushPromises()

    expect(run).toHaveBeenCalledTimes(1)
    expect(document.body.querySelector('[data-testid="action-dialog"]')).toBeNull()
    wrapper.unmount()
  })

  it("opens the window when the source refuses, because the answer is there", async () => {
    vi.spyOn(ConnectorsService, "runAction").mockRejectedValue(refused(409))
    const wrapper = mountDialog(PASTE, ["reports"])
    await flushPromises()

    expect(document.body.querySelector('[data-testid="action-dialog"]')).not.toBeNull()
    expect(text("action-error")).not.toBe("")
    wrapper.unmount()
  })
})
