import { describe, expect, it } from "vitest"

import type { ActionInfo } from "@/client"
import { at, first } from "@/shared/testing/collections"
import { replacementsOf, reloadedBy, summarize, toCommands, toMenu } from "./actions"

const only = (actions: ActionInfo[]) => first(toCommands(actions))

const createFolder: ActionInfo = {
  name: "create_folder",
  title: "New folder",
  destructive: false,
  takes_file: false,
  takes_many_files: false,
  previews: false,
  downloads: false,
  acts_on: "children",
  applicable: true,
  params_schema: {
    type: "object",
    properties: { name: { type: "string", title: "Name", default: "new folder" } },
  },
}

const remove: ActionInfo = {
  name: "delete",
  title: "Delete",
  destructive: true,
  takes_file: false,
  takes_many_files: false,
  previews: false,
  downloads: false,
  acts_on: "node",
  applicable: true,
  params_schema: {
    type: "object",
    properties: {},
  },
}

const upload: ActionInfo = {
  name: "upload",
  title: "Upload files",
  destructive: false,
  takes_file: true,
  takes_many_files: true,
  previews: false,
  downloads: false,
  acts_on: "children",
  applicable: true,
  params_schema: {
    type: "object",
    properties: {
      conflict: {
        type: "string",
        title: "File conflict",
        default: "refuse",
        enum: ["refuse", "replace", "rename"],
        "x-ui-hidden": true,
        "x-ui-purpose": "file-conflict",
      },
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
    expect(at(command.fields, 0).defaultValue).toBe("new folder")
  })

  it("keeps workflow-only parameters out of the visible form", () => {
    expect(at(only([upload]).fields, 0).kind).toBe("hidden")
  })

  it("marks what destroys something, so the dialog can ask twice", () => {
    expect(only([remove]).destructive).toBe(true)
    expect(only([createFolder]).destructive).toBe(false)
  })

  it("marks what needs a file to be chosen", () => {
    expect(only([upload]).takesFile).toBe(true)
  })

  it("marks what may be handed several files at once", () => {
    // The picker offers a set or one file by this, never by the name of
    // the action: loading a table from a CSV takes one file, and the
    // server is what says so.
    expect(only([upload]).takesManyFiles).toBe(true)
    expect(only([createFolder]).takesManyFiles).toBe(false)
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
      takes_many_files: false,
      previews: true,
      downloads: true,
      acts_on: "node",
      applicable: true,
      params_schema: { type: "object", properties: {} },
    }

    const command = only([invented])

    expect(command.label).toBe("Extract")
    expect(command.fields).toEqual([])
    // Whether it can say what it would do is the server's statement too.
    expect(command.previews).toBe(true)
    expect(command.downloads).toBe(true)
  })
})

describe("toMenu", () => {
  const vocabulary = [createFolder, upload, remove]
  const named = (commands: { name: string }[]) => commands.map((command) => command.name)
  const enabled = (commands: { name: string; enabled: boolean }[]) =>
    named(commands.filter((command) => command.enabled))

  it("keeps the whole action vocabulary visible in the current place", () => {
    const menu = toMenu(vocabulary, [], ["reports"], [])

    expect(named(menu)).toEqual(["create_folder", "upload", "delete"])
  })

  it("disables what changes a node until one is ticked", () => {
    /* Standing in a folder is not choosing it. */
    const menu = toMenu(vocabulary, [], ["reports"], [])

    expect(enabled(menu)).toEqual(["create_folder", "upload"])
  })

  it("turns on what the server says the ticked nodes admit", () => {
    const menu = toMenu(vocabulary, [{ ...remove, applicable: true }], ["reports"], [
      "reports/q3.csv",
    ])

    expect(enabled(menu)).toEqual(["create_folder", "upload", "delete"])
  })

  it("disables what the server refuses for the ticked nodes", () => {
    const menu = toMenu(vocabulary, [{ ...remove, applicable: false }], [null], ["", "a"])

    expect(enabled(menu)).toEqual(["create_folder", "upload"])
  })

  it("disables what does not apply to the level being looked at", () => {
    const menu = toMenu(
      [{ ...createFolder, applicable: false }, upload, remove],
      [],
      ["notes.txt"],
      []
    )

    expect(named(menu)).toEqual(["create_folder", "upload", "delete"])
    expect(enabled(menu)).toEqual(["upload"])
  })

  it("sends what changes a node to the ticked ones, and the rest to the level", () => {
    const menu = toMenu(vocabulary, [remove], ["reports"], ["reports/q3.csv"])
    const targets = Object.fromEntries(menu.map((command) => [command.name, command.targets]))

    expect(targets).toEqual({
      create_folder: ["reports"],
      upload: ["reports"],
      delete: ["reports/q3.csv"],
    })
  })

  it("names the root as null when that is the level", () => {
    const menu = toMenu(vocabulary, [], [null], [])

    expect(at(menu, 0).targets).toEqual([null])
  })

  it("sends what is made inside to every place whose contents are shown", () => {
    /* A schema is a grouping rather than a folder, and two of them ticked is
       two places — which is why a form that is not bulk goes grey there. */
    const menu = toMenu(vocabulary, [], ["public", "demo_lab"], [])
    const targets = Object.fromEntries(menu.map((command) => [command.name, command.targets]))

    expect(targets.upload).toEqual(["public", "demo_lab"])
  })

  it("offers nothing to make when there is nowhere to make it", () => {
    const menu = toMenu(vocabulary, [], [], [])

    expect(enabled(menu)).toEqual([])
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

  it("keeps source-issued node replacements", () => {
    const replacement = {
      old_node_id: "public.orders",
      new_node_id: "public.sales",
      title: "sales",
    }
    const outcome = {
      done: [{ ...result("renamed", "public"), replacement }],
      failures: [],
      total: 1,
    }

    expect(replacementsOf(outcome)).toEqual([replacement])
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

  it("names the file a refusal was about, not the folder it went into", () => {
    // Three files into one folder are three requests about the same node,
    // so naming the node would not say which of them was refused.
    const outcome = {
      done: [result("first.csv uploaded", "reports")],
      failures: [
        {
          nodeId: "reports",
          message: "second.csv is already there",
          file: new File(["id"], "second.csv"),
          conflict: true,
        },
      ],
      total: 2,
    }

    expect(summarize(outcome, "Upload files")).toBe(
      "Upload files: 1 of 2. second.csv — second.csv is already there"
    )
  })
})
