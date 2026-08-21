import { describe, expect, it } from "vitest"

import type { ActionInfo } from "@/client"
import { toCommands } from "./actions"
import type { ActionCommand } from "./actions"

function only(actions: ActionInfo[]): ActionCommand {
  const [command] = toCommands(actions)
  if (!command) throw new Error("no command was built")
  return command
}

function fieldOf(command: ActionCommand, index: number) {
  const field = command.fields[index]
  if (!field) throw new Error(`no field at ${index}`)
  return field
}

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
    expect(fieldOf(command, 0).required).toBe(true)
  })

  it("reads a boolean parameter as a checkbox", () => {
    expect(fieldOf(only([remove]), 0).kind).toBe("boolean")
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
