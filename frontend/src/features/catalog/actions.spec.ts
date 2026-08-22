import { describe, expect, it } from "vitest"

import type { ActionInfo } from "@/client"
import { at, first } from "@/shared/testing/collections"
import { reloadedBy, summarize, toCommands } from "./actions"

const only = (actions: ActionInfo[]) => first(toCommands(actions))

const createFolder: ActionInfo = {
  name: "create_folder",
  title: "New folder",
  destructive: false,
  takes_file: false,
  params_schema: {
    type: "object",
    required: ["name"],
    properties: { name: { type: "string", title: "Name" } },
  },
}

const remove: ActionInfo = {
  name: "delete",
  title: "Delete",
  destructive: true,
  takes_file: false,
  params_schema: {
    type: "object",
    properties: {
      recursive: {
        type: "boolean",
        title: "Delete everything inside",
        default: false,
      },
    },
  },
}

const upload: ActionInfo = {
  name: "upload",
  title: "Upload a file",
  destructive: false,
  takes_file: true,
  params_schema: {
    type: "object",
    properties: {
      overwrite: { type: "boolean", title: "Replace an existing file", default: false },
    },
  },
}

describe("toCommands", () => {
  it("keeps the label the server gave", () => {
    expect(only([createFolder]).label).toBe("New folder")
  })

  it("builds the fields of the form from the schema of the parameters", () => {
    const command = only([createFolder])

    expect(command.fields.map((field) => field.name)).toEqual(["name"])
    expect(at(command.fields, 0).required).toBe(true)
  })

  it("reads a boolean parameter as a checkbox", () => {
    expect(at(only([remove]).fields, 0).kind).toBe("boolean")
  })

  it("marks what destroys something, so the dialog can ask twice", () => {
    expect(only([remove]).destructive).toBe(true)
    expect(only([createFolder]).destructive).toBe(false)
  })

  it("marks what needs a file to be chosen", () => {
    expect(only([upload]).takesFile).toBe(true)
  })

  it("keeps the order the server sent", () => {
    const names = toCommands([upload, createFolder, remove]).map(
      (command) => command.name
    )

    expect(names).toEqual(["upload", "create_folder", "delete"])
  })

  it("has no knowledge of any particular action", () => {
    /* A source can add an action tomorrow; nothing here is keyed by name. */
    const invented: ActionInfo = {
      name: "extract_archive",
      title: "Extract",
      destructive: false,
      takes_file: false,
      params_schema: { type: "object", properties: {} },
    }

    const command = only([invented])

    expect(command.label).toBe("Extract")
    expect(command.fields).toEqual([])
  })
})

describe("what became of a set", () => {
  const result = (message: string, reload: string | null) => ({
    message,
    reload_node_id: reload,
  })

  it("names each branch to re-read once", () => {
    const outcome = {
      done: [result("a gone", "reports"), result("b gone", "reports"), result("c gone", null)],
      failures: [],
      total: 3,
    }

    expect(reloadedBy(outcome)).toEqual(["reports", null])
  })

  it("says what the server said when one node was acted on", () => {
    const outcome = { done: [result("notes.txt deleted", null)], failures: [], total: 1 }

    expect(summarize(outcome, "Delete")).toBe("notes.txt deleted")
  })

  it("counts when there were several", () => {
    const outcome = {
      done: [result("a", null), result("b", null)],
      failures: [],
      total: 2,
    }

    expect(summarize(outcome, "Delete")).toBe("Delete: 2 of 2")
  })

  it("names what was refused, and by whom", () => {
    const outcome = {
      done: [result("a", null)],
      failures: [{ nodeId: "reports", message: "not empty" }],
      total: 2,
    }

    expect(summarize(outcome, "Delete")).toBe("Delete: 1 of 2. reports — not empty")
  })
})
