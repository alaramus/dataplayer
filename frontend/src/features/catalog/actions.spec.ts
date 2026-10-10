import { describe, expect, it } from "vitest"

import type { ActionInfo } from "@/client"
import { at, first } from "@/shared/testing/collections"
import {
  clientCommandOf,
  clientMenu,
  groupingChoices,
  nodeSetOf,
  replacementsOf,
  reloadedBy,
  summarize,
  ticksAfter,
  toCommands,
  toMenu as resolveMenu,
  withFieldChoices,
  withGroupingChoices,
  withSubmenus,
} from "./actions"

function toMenu(
  level: ActionInfo[],
  here: ActionInfo[],
  picked: ActionInfo[],
  levelId: string | null,
  places: (string | null)[],
  nodeTargets: string[]
) {
  return resolveMenu({
    level: { actions: level, targets: [levelId] },
    children: { actions: here, targets: places },
    node: { actions: picked, targets: nodeTargets },
    group: { actions: [], targets: [] },
    destination: { actions: [], targets: [] },
  })
}

const only = (actions: ActionInfo[]) => first(toCommands(actions))

it("derives mandatory plan review while older action payloads stay optional", () => {
  expect(only([createFolder]).requiresPlanReview).toBe(false)
  expect(only([{ ...createFolder, requires_plan_review: true }]).requiresPlanReview).toBe(true)
})

it("reads the job transport off the answer, and an older answer as none", () => {
  expect(only([createFolder]).producesJob).toBe(false)
  expect(only([{ ...createFolder, produces_job: true }]).producesJob).toBe(true)
})

const createFolder: ActionInfo = {
  name: "create_folder",
  title: "New folder",
  destructive: false,
  takes_file: false,
  takes_many_files: false,
  previews: false,
  takes_set: false,
  previews_set: false,
  downloads: false,
  acts_on: "children",
  offered_in: "catalog",
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
  takes_set: false,
  previews_set: false,
  downloads: false,
  acts_on: "node",
  offered_in: "catalog",
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
  takes_set: false,
  previews_set: false,
  downloads: false,
  acts_on: "children",
  offered_in: "catalog",
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
  it("recognizes a connector draft by capability rather than action name", () => {
    const sourceAction: ActionInfo = {
      ...remove,
      name: "source_specific_connection",
      title: "Connect this node",
      destructive: false,
      prepares_connector: true,
    }
    expect(only([sourceAction]).preparesConnector).toBe(true)
    expect(only([remove]).preparesConnector).toBe(false)
    expect(first(toMenu([sourceAction], [], [], null, [null], [])).enabled).toBe(false)
    const picked = first(toMenu([sourceAction], [], [sourceAction], null, [null], ["folder"]))
    expect(picked.enabled).toBe(true)
    expect(picked.targets).toEqual(["folder"])
  })

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
      takes_set: false,
      previews_set: false,
      downloads: true,
      acts_on: "node",
      offered_in: "catalog",
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
  const menu = (
    here: ActionInfo[],
    picked: ActionInfo[],
    places: (string | null)[],
    nodeTargets: string[]
  ) => toMenu(vocabulary, here, picked, null, places, nodeTargets)
  const named = (commands: { name: string }[]) => commands.map((command) => command.name)
  const enabled = (commands: { name: string; enabled: boolean }[]) =>
    named(commands.filter((command) => command.enabled))

  it("keeps the whole action vocabulary visible in the current place", () => {
    const commands = menu(vocabulary, [], ["reports"], [])

    expect(named(commands)).toEqual(["create_folder", "upload", "delete"])
  })

  it("leaves out what the source wants offered above a node's own rows", () => {
    /* Drawn there instead, not in both places: one command in two menus is
       two menus to keep in step. */
    const createRole: ActionInfo = {
      ...remove,
      name: "create_role",
      title: "New role",
      destructive: false,
      offered_in: "rows",
    }

    const commands = toMenu(
      [...vocabulary, createRole],
      [],
      [createRole],
      null,
      ["reports"],
      ["roles"]
    )

    expect(named(commands)).toEqual(["create_folder", "upload", "delete"])
  })

  it("disables what changes a node until one is ticked", () => {
    /* Standing in a folder is not choosing it. */
    const commands = menu(vocabulary, [], ["reports"], [])

    expect(enabled(commands)).toEqual(["create_folder", "upload"])
  })

  it("says which of the two things a greyed line is missing", () => {
    // A greyed line and a barred cursor name no remedy, and there are three
    // different ones: tick something, stand somewhere else, or nothing —
    // this source cannot do it here at all.
    const nothingTicked = menu(vocabulary, [], ["reports"], [])
    const refused = menu(vocabulary, [], ["reports"], ["reports/q3.csv"])
    const reasons = (commands: { name: string; reason: string | null }[]) =>
      Object.fromEntries(commands.map((command) => [command.name, command.reason]))

    expect(reasons(nothingTicked).delete).toBe("Tick a row to use this")
    expect(reasons(refused).delete).toBe("This source does not offer it for these targets")
    // What is available says nothing: a reason under a line that works is noise.
    expect(reasons(nothingTicked).upload).toBeNull()
  })

  it("says there is nowhere to put a thing when the level offers no place", () => {
    const commands = menu(vocabulary, [], [], [])
    const upload = commands.find((command) => command.name === "upload")

    expect(upload?.enabled).toBe(false)
    expect(upload?.reason).toBe("There is nowhere here to put it")
  })

  it("turns on what the server says the ticked nodes admit", () => {
    const commands = menu(vocabulary, [{ ...remove, applicable: true }], ["reports"], [
      "reports/q3.csv",
    ])

    expect(enabled(commands)).toEqual(["create_folder", "upload", "delete"])
  })

  it("disables what the server refuses for the ticked nodes", () => {
    const commands = menu(vocabulary, [{ ...remove, applicable: false }], [null], ["", "a"])

    expect(enabled(commands)).toEqual(["create_folder", "upload"])
  })

  it("disables what does not apply to the level being looked at", () => {
    const commands = menu(
      [{ ...createFolder, applicable: false }, upload, remove],
      [],
      ["notes.txt"],
      []
    )

    expect(named(commands)).toEqual(["create_folder", "upload", "delete"])
    expect(enabled(commands)).toEqual(["upload"])
  })

  it("sends what changes a node to the ticked ones, and the rest to the level", () => {
    const commands = menu(vocabulary, [remove], ["reports"], ["reports/q3.csv"])
    const targets = Object.fromEntries(commands.map((command) => [command.name, command.targets]))

    expect(targets).toEqual({
      create_folder: ["reports"],
      upload: ["reports"],
      delete: ["reports/q3.csv"],
    })
  })

  it("names the root as null when that is the level", () => {
    const commands = menu(vocabulary, [], [null], [])

    expect(at(commands, 0).targets).toEqual([null])
  })

  it("sends what is made inside to every place whose contents are shown", () => {
    /* A schema is a grouping rather than a folder, and two of them ticked is
       two places — which is why a form that is not bulk goes grey there. */
    const commands = menu(vocabulary, [], ["public", "demo_lab"], [])
    const targets = Object.fromEntries(commands.map((command) => [command.name, command.targets]))

    expect(targets.upload).toEqual(["public", "demo_lab"])
  })

  it("offers nothing to make when there is nowhere to make it", () => {
    const commands = menu(vocabulary, [], [], [])

    expect(enabled(commands)).toEqual([])
  })

  it("keeps an action on the level separate from selected groupings", () => {
    const createSchema: ActionInfo = {
      ...createFolder,
      name: "create_schema",
      title: "New schema",
      acts_on: "level",
      offered_in: "catalog",
    }

    const commands = toMenu(
      [createSchema],
      [{ ...createSchema, applicable: false }],
      [],
      null,
      ["public"],
      ["public"]
    )

    expect(at(commands, 0).enabled).toBe(true)
    expect(at(commands, 0).targets).toEqual([null])
  })

  it("resolves groupings independently of checked rows and keeps destination workflows singular", () => {
    const rename: ActionInfo = { ...remove, name: "rename_schema", acts_on: "group" }
    const load: ActionInfo = { ...upload, name: "load_csv", acts_on: "destination" }
    const commands = resolveMenu({
      level: { actions: [rename, load, remove], targets: [null] },
      children: { actions: [], targets: ["schema"] },
      node: { actions: [remove], targets: ["schema.a", "schema.b"] },
      group: { actions: [rename], targets: ["schema"] },
      destination: {
        actions: [{ ...load, available_node_ids: ["schema", "other"] }],
        targets: ["schema", "system", "other"],
      },
    })
    expect(commands.map(({ name, enabled, targets }) => ({ name, enabled, targets }))).toEqual([
      { name: "rename_schema", enabled: true, targets: ["schema"] },
      { name: "load_csv", enabled: true, targets: ["schema"] },
      { name: "delete", enabled: true, targets: ["schema.a", "schema.b"] },
    ])
  })

  it("shows the server's cardinality reason without replacing or trimming the selection", () => {
    const rename: ActionInfo = { ...remove, name: "rename_schema", acts_on: "group" }
    const commands = resolveMenu({
      level: { actions: [rename], targets: [null] },
      children: { actions: [], targets: [] },
      node: { actions: [], targets: ["table"] },
      group: {
        actions: [{ ...rename, applicable: false, unavailable_reason: "Select one grouping to use this" }],
        targets: ["one", "two"],
      },
      destination: { actions: [], targets: [] },
    })
    expect(first(commands)).toMatchObject({
      enabled: false,
      targets: ["one", "two"],
      reason: "Select one grouping to use this",
    })
  })

  it("does not turn the current folder into an explicit grouping selection", () => {
    const rename: ActionInfo = { ...remove, acts_on: "group" }
    const commands = resolveMenu({
      level: { actions: [rename], targets: ["folder"] },
      children: { actions: [rename], targets: ["folder"] },
      node: { actions: [], targets: [] },
      group: { actions: [rename], targets: [] },
      destination: { actions: [], targets: [] },
    })
    expect(first(commands)).toMatchObject({ enabled: false, targets: [], reason: "Select a grouping to use this" })
  })

  it("keeps creation available without displayed schemas and refuses missing availability", () => {
    const load: ActionInfo = { ...upload, name: "load_csv", acts_on: "destination" }
    const subjects = {
      level: { actions: [load], targets: [null] },
      children: { actions: [], targets: [] },
      node: { actions: [], targets: [] },
      group: { actions: [], targets: [] },
      destination: {
        actions: [{ ...load, available_node_ids: ["writable"] }],
        targets: ["system", "writable"],
      },
    }
    expect(first(resolveMenu(subjects))).toMatchObject({ enabled: true, targets: ["writable"] })
    expect(first(resolveMenu({ ...subjects, destination: { actions: [], targets: ["writable"] } })))
      .toMatchObject({ enabled: false, targets: [] })
  })
})

describe("what became of a set", () => {
  const result = (message: string, reload: string | null) => ({
    message,
    reload_node_ids: [reload],
  })

  it("names each branch to re-read once", () => {
    const outcome = {
      done: [
        result("a gone", "reports"),
        { message: "moved", reload_node_ids: ["reports", "archive"] },
        result("c gone", null),
      ],
      failures: [],
      total: 3,
    }

    expect(reloadedBy(outcome)).toEqual(["reports", "archive", null])
  })

  it("leaves ticked only what the action could not be carried out on", () => {
    const outcome = {
      done: [result("a gone", "reports")],
      failures: [{ nodeId: "b", message: "refused" }],
      skipped: [{ nodeId: "c", message: "not sent" }],
      total: 3,
    }

    expect(ticksAfter(["a", "b", "c"], outcome)).toEqual(["b", "c"])
  })

  it("takes every tick off once everything was done", () => {
    const outcome = { done: [result("a gone", "reports")], failures: [], total: 1 }

    expect(ticksAfter(["a", "b"], outcome)).toEqual([])
  })

  it("leaves the ticks alone when nothing was done at all", () => {
    const outcome = { done: [], failures: [{ nodeId: null, message: "refused" }], total: 1 }

    expect(ticksAfter(["a", "b"], outcome)).toEqual(["a", "b"])
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

/**
 * A field that names a schema is a choice, and the schema cannot say so.
 *
 * The list belongs to one connection and the action's parameters are declared
 * by a class, so the server says what the field means and the level says what
 * there is. Between them the reader picks a name instead of spelling one.
 */
describe("a field that names a grouping", () => {
  const groupings = [
    { id: "public", label: "public", system: false },
    { id: "pg_catalog", label: "pg_catalog", system: true },
    { id: "reports", label: "reports", system: false },
  ]

  const field = {
    name: "target_schema",
    label: "Target schema",
    kind: "text" as const,
    required: true,
    purpose: "grouping" as const,
    group: "general",
  }

  it("leaves out what the source calls its own", () => {
    expect(groupingChoices(groupings)).toEqual([
      { value: "public", label: "public" },
      { value: "reports", label: "reports" },
    ])
  })

  it("becomes a choice of what this connection holds", () => {
    const [changed] = withGroupingChoices([field], groupingChoices(groupings))

    expect(changed?.kind).toBe("select")
    expect(changed?.choices?.map((choice) => choice.value)).toEqual(["public", "reports"])
  })

  it("stays a box to type in when there is nothing to choose from", () => {
    // A file source offers no groupings, and a select with no options is a
    // dead end where a typed name would still have been answered.
    expect(withGroupingChoices([field], groupingChoices([]))).toEqual([field])
  })

  it("leaves every other field alone", () => {
    const name = { ...field, name: "new_name", purpose: "node-name" as const }

    expect(withGroupingChoices([name], groupingChoices(groupings))).toEqual([name])
  })
})

describe("what counts as a set", () => {
  it("is every ticked node when they are all named", () => {
    expect(nodeSetOf(["public.orders", "public.items"])).toEqual([
      "public.orders",
      "public.items",
    ])
  })

  it("is not a set when the root of the connector is in it", () => {
    // The root travels as null and has no id to put in a list.
    expect(nodeSetOf([null, "public.orders"])).toBeNull()
    expect(nodeSetOf([null])).toBeNull()
  })

  it("is not a set when nothing is ticked", () => {
    expect(nodeSetOf([])).toBeNull()
  })
})

describe("the client's own lines of the menu", () => {
  const everything = {
    describes: true, describable: true, diagrams: true, diagrammable: true,
    copy: { enabled: true }, cut: { enabled: true },
  }
  const nothingTicked = { enabled: false, reason: "Tick a row to use this" }

  it("puts the four the client owns before the source's own", () => {
    const items = clientMenu(everything)

    expect(items.map((item) => item.label)).toEqual([
      "Details",
      "Relationships",
      "Copy",
      "Cut",
    ])
    expect(items.every((item) => item.disable === false)).toBe(true)
  })

  it("puts the one line about the connection after the ones about its nodes", () => {
    const items = clientMenu({ ...everything, backups: { enabled: true } })

    expect(items.map((item) => item.label)).toEqual([
      "Details",
      "Relationships",
      "Copy",
      "Cut",
      "Backups",
    ])
  })

  it("leaves out copying a source out that cannot be copied out", () => {
    // A file source declares no `backup` capability, and a line that can never
    // work is worse than no line.
    expect(clientMenu(everything).map((item) => item.label)).not.toContain("Backups")
  })

  it("keeps the line and says why when the server cannot copy anything out", () => {
    const items = clientMenu({
      ...everything,
      backups: { enabled: false, reason: "This server cannot copy a database out" },
    })
    const backups = items.find((item) => item.label === "Backups")

    expect(backups?.disable).toBe(true)
    expect(backups?.hint).toBe("This server cannot copy a database out")
  })

  it("leaves out what a source has no use for", () => {
    // A key store describes no nodes, draws none of them and has nothing
    // anything else could take.
    const items = clientMenu({ describes: false, describable: false, diagrams: false, diagrammable: false })

    expect(items).toEqual([])
  })

  it("draws Copy without Cut for a source whose nodes can only be copied out", () => {
    // A table pastes into a folder as a file, and is never removed by it (D165).
    const items = clientMenu({ ...everything, cut: undefined })

    expect(items.map((item) => item.label)).toEqual(["Details", "Relationships", "Copy"])
  })

  it("says why a selection cannot be put on the clipboard", () => {
    const items = clientMenu({
      ...everything, copy: { enabled: false, reason: "Copy one table at a time" },
    })
    const copy = items.find((item) => item.label === "Copy")

    expect(copy?.disable).toBe(true)
    expect(copy?.hint).toBe("Copy one table at a time")
  })

  it("keeps a line and disables it while the selection is not the one it needs", () => {
    // A diagram of nothing, and a diagram of more than one holds, are the two
    // ways that line is not the one to offer, and neither hides it.
    const items = clientMenu({
      ...everything, describable: false, diagrammable: false,
      copy: nothingTicked, cut: nothingTicked,
    })

    expect(items.map((item) => item.disable)).toEqual([true, true, true, true])
  })

  it("says under each greyed line what would make it usable", () => {
    const items = clientMenu({
      ...everything, describable: false, diagrammable: false,
      copy: nothingTicked, cut: nothingTicked,
    })

    expect(items.map((item) => item.hint)).toEqual([
      "Tick one row to describe",
      "Nothing here has a structure to draw",
      "Tick a row to use this",
      "Tick a row to use this",
    ])
  })

  it("says nothing under a line that works", () => {
    expect(clientMenu(everything).every((item) => item.hint === undefined)).toBe(true)
  })

  it("tells its own command from a source's by the one thing a name cannot be", () => {
    // A source names its actions with identifiers, so a colon cannot collide.
    expect(clientCommandOf("client:copy")).toBe("copy")
    expect(clientCommandOf("copy")).toBeNull()
    expect(clientCommandOf("paste")).toBeNull()
  })
})

describe("a family of commands the source names", () => {
  it("folds into one submenu where its first line stood", () => {
    const menu = withSubmenus([
      { name: "client:details", label: "Details" },
      { name: "timescale_design_hypertable", label: "Hypertable settings", group: "Timescale" },
      { name: "drop_relation", label: "Drop", group: null },
      { name: "timescale_set_chunk_interval", label: "Change chunk interval", group: "Timescale", disable: true },
    ])

    expect(menu.map((line) => line.name)).toEqual(["client:details", "group:Timescale", "drop_relation"])
    const family = at(menu, 1)
    expect(family.label).toBe("Timescale")
    expect(family.disable).toBe(false)
    expect(family.children?.map((line) => line.name)).toEqual([
      "timescale_design_hypertable", "timescale_set_chunk_interval",
    ])
  })

  it("is disabled only when every line in it is", () => {
    const [family] = withSubmenus([
      { name: "a", label: "A", group: "Timescale", disable: true, hint: "Not a hypertable" },
    ])
    expect(family?.disable).toBe(true)
    expect(family?.children?.[0]?.hint).toBe("Not a hypertable")
  })
})

describe("choices the source names for one node", () => {
  const column = {
    name: "column",
    label: "Column",
    kind: "text" as const,
    required: true,
    group: "general",
  }
  const amount = { ...column, name: "amount", kind: "number" as const }

  it("turns a typed name into a list of what the node has", () => {
    const [changed] = withFieldChoices([column], { column: [{ value: "value", label: "value · integer" }] })
    expect(changed).toMatchObject({ kind: "select", choices: [{ value: "value", label: "value · integer" }] })
  })

  it("keeps a field typed when nothing was named for it, or before the answer", () => {
    expect(withFieldChoices([column], { column: [] })).toEqual([column])
    expect(withFieldChoices([column], undefined)).toEqual([column])
    expect(withFieldChoices([amount], { amount: [{ value: "1", label: "1" }] })).toEqual([amount])
  })
})

