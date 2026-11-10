import { createConnectorKey, deleteConnectorKey, makeConnectorHereKey } from "@/features/connectors/api"
import { runActionKey } from "@/features/catalog/api"
import { updateCellKey } from "@/features/grid/api"
import { startRunKey } from "@/features/queries/runs"
import { t } from "@/shared/i18n"

import { isRecord, say, splitPath, testId, testIdPrefix } from "./tour"
import type { TourChapter, TourDefinition, TourMemory } from "./tour"

/**
 * The first tour: a SQLite database made, worked with and cleaned away, then
 * a server shown that could be started here (D355). Every target is a `data-testid` the Playwright scenarios
 * hold on to as well; `tests/onboarding.spec.ts` walks this whole list.
 */

/** The table of the lab (D261) the middle chapters work on. */
export const TOUR_TABLE = "tasks"
/** The column whose cell is changed. */
export const TOUR_COLUMN = "title"
/** The service the last chapter shows and does not start. */
export const SERVICE_SHOWN = "redis"

const database = (memory: TourMemory) => memory.database ?? null

/** The catalog's tick box is a Quasar checkbox: the state is on its own element. */
function ticked(selector: string, find: (selector: string) => Element | null): boolean {
  return find(selector)?.getAttribute("aria-checked") === "true"
}

const made: TourChapter = {
  id: "make",
  title: say("onboarding.tour.make.title"),
  targets: [
    { locate: () => testId("add-connector"), hint: say("onboarding.tour.make.add") },
    { locate: () => testId("adapter-sqlite"), hint: say("onboarding.tour.make.pick") },
    { locate: () => testId("make-here"), hint: say("onboarding.tour.make.here") },
    { locate: () => testId("make-here-submit"), hint: say("onboarding.tour.make.submit") },
  ],
  done: {
    kind: "mutation",
    key: makeConnectorHereKey,
    settle: ({ data }, memory) => {
      if (!isRecord(data) || typeof data.id !== "string" || typeof data.name !== "string") return null
      const config = isRecord(data.config) ? data.config : {}
      const path = typeof config.path === "string" ? config.path : ""
      return { ...memory, database: { id: data.id, name: data.name, ...splitPath(path) } }
    },
  },
}

const opened: TourChapter = {
  id: "open",
  title: say("onboarding.tour.open.title"),
  targets: [
    {
      locate: (memory) => (database(memory) ? testId(`connector-${database(memory)?.name}`) : null),
      hint: say("onboarding.tour.open.connection"),
    },
    { locate: () => testId(`catalog-node-${TOUR_TABLE}`), hint: say("onboarding.tour.open.table", { table: TOUR_TABLE }) },
  ],
  done: {
    kind: "shown",
    locate: (memory) => {
      const made = database(memory)
      return made ? testIdPrefix(`workspace-tab-rows:${made.id}:`) : null
    },
  },
}

const filtered: TourChapter = {
  id: "filter",
  title: say("onboarding.tour.filter.title"),
  targets: [
    { locate: () => testId("grid-filter"), hint: say("onboarding.tour.filter.open") },
    { locate: () => testId("grid-filter-editor"), hint: say("onboarding.tour.filter.fill") },
  ],
  done: { kind: "shown", locate: () => testId("grid-filter-count") },
}

const edited: TourChapter = {
  id: "edit",
  title: say("onboarding.tour.edit.title"),
  targets: [
    {
      // Whichever row is first after the filter: its place, not its key.
      locate: () => `${testIdPrefix("grid-cell-")}[data-testid$="-${TOUR_COLUMN}"]`,
      hint: say("onboarding.tour.edit.cell"),
    },
    { locate: () => testId("grid-cell-editor"), hint: say("onboarding.tour.edit.save") },
  ],
  done: { kind: "mutation", key: updateCellKey, settle: (_, memory) => memory },
}

const queried: TourChapter = {
  id: "query",
  title: say("onboarding.tour.query.title"),
  targets: [
    { locate: () => testId("grid-query"), hint: say("onboarding.tour.query.open") },
    { locate: () => testId("query-run"), hint: say("onboarding.tour.query.run") },
  ],
  done: {
    kind: "mutation",
    key: startRunKey,
    settle: ({ variables }, memory) =>
      isRecord(variables) && variables.connector_id === database(memory)?.id ? memory : null,
  },
}

const disconnected: TourChapter = {
  id: "disconnect",
  title: say("onboarding.tour.disconnect.title"),
  targets: [
    {
      locate: (memory) => (database(memory) ? testId(`connector-edit-${database(memory)?.name}`) : null),
      hint: say("onboarding.tour.disconnect.edit"),
    },
    // The window keeps a copy of its form out of the tab order while it opens.
    { locate: () => `${testId("delete-connector")}[tabindex="0"]`, hint: say("onboarding.tour.disconnect.delete") },
    { locate: () => testId("confirm-accept"), hint: say("onboarding.tour.disconnect.confirm") },
  ],
  done: {
    kind: "mutation",
    key: deleteConnectorKey,
    settle: ({ variables }, memory) => (variables === database(memory)?.id ? memory : null),
  },
}

const connected: TourChapter = {
  id: "folder",
  title: say("onboarding.tour.folder.title"),
  targets: [
    { locate: () => testId("add-connector"), hint: say("onboarding.tour.folder.add") },
    { locate: () => testId("adapter-file"), hint: say("onboarding.tour.folder.pick") },
    {
      locate: () => testId("create-from-catalog"),
      hint: say("onboarding.tour.folder.create"),
      ready: (_, find) => find(`${testId("adapter-file")}[aria-pressed="true"]`) !== null,
    },
    { locate: () => testId("save-connector"), hint: say("onboarding.tour.folder.save") },
  ],
  done: {
    kind: "mutation",
    key: createConnectorKey,
    settle: ({ variables, data }, memory) => {
      if (!isRecord(variables) || variables.adapter_type !== "file") return null
      if (!isRecord(data) || typeof data.id !== "string" || typeof data.name !== "string") return null
      return { ...memory, folder: { id: data.id, name: data.name } }
    },
  },
}

const found: TourChapter = {
  id: "find",
  title: say("onboarding.tour.find.title"),
  targets: [
    {
      locate: (memory) => (memory.folder ? testId(`connector-${memory.folder.name}`) : null),
      hint: say("onboarding.tour.find.connection"),
    },
    {
      locate: (memory) => {
        const top = database(memory)?.folder.split("/")[0]
        return top ? testId(`catalog-node-${top}`) : null
      },
      hint: (memory) => t("onboarding.tour.find.folder", { folder: database(memory)?.folder ?? "" }),
    },
  ],
  done: {
    kind: "shown",
    locate: (memory) => (database(memory)?.file ? testId(`catalog-node-${database(memory)?.file}`) : null),
  },
}

const removed: TourChapter = {
  id: "remove",
  title: say("onboarding.tour.remove.title"),
  targets: [
    {
      locate: (memory) => (database(memory)?.file ? testId(`catalog-check-${database(memory)?.file}`) : null),
      hint: (memory) => t("onboarding.tour.remove.tick", { file: database(memory)?.file ?? "" }),
    },
    {
      locate: () => testId("catalog-actions"),
      hint: say("onboarding.tour.remove.actions"),
      ready: (memory, find) => {
        const file = database(memory)?.file
        return file !== undefined && ticked(testId(`catalog-check-${file}`), find)
      },
    },
    { locate: () => testId("menu-item-delete"), hint: say("onboarding.tour.remove.delete") },
    { locate: () => testId("action-submit"), hint: say("onboarding.tour.remove.confirm") },
  ],
  done: {
    kind: "mutation",
    key: runActionKey,
    settle: ({ variables, data }, memory) => {
      const file = database(memory)?.file
      if (file === undefined || !isRecord(variables) || variables.name !== "delete") return null
      const nodes = Array.isArray(variables.nodeIds) ? variables.nodeIds : []
      const aimed = nodes.some((node) => typeof node === "string" && node.split("/").pop() === file)
      const failed = isRecord(data) && Array.isArray(data.failures) && data.failures.length > 0
      return aimed && !failed ? memory : null
    },
  },
}

/**
 * The last chapter only shows: a server this application starts in Docker,
 * Redis because nothing before looked like it. The tour starts nothing: it
 * ends on Finish, or on the person pressing the start button themselves.
 */
const served: TourChapter = {
  id: "service",
  title: say("onboarding.tour.service.title"),
  targets: [
    { locate: () => testId("add-connector"), hint: say("onboarding.tour.service.add") },
    { locate: () => testId("adapter-redis"), hint: say("onboarding.tour.service.pick") },
    {
      locate: () => testId(`start-service-${SERVICE_SHOWN}`),
      hint: say("onboarding.tour.service.start"),
      ready: (_, find) => find(`${testId(`adapter-${SERVICE_SHOWN}`)}[aria-pressed="true"]`) !== null,
      pressCompletes: true,
    },
  ],
  done: { kind: "next" },
}

export const BASICS_TOUR: TourDefinition = {
  id: "basics",
  title: () => t("onboarding.tours.basics.title"),
  summary: () => t("onboarding.tours.basics.summary"),
  chapters: [made, opened, filtered, edited, queried, disconnected, connected, found, removed, served],
}
