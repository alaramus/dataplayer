import { createPipelineKey } from "@/features/pipelines/api"

import { TOUR_TABLE } from "./basics"
import { inCatalog, isRecord, rememberDatabase, say, testId, testIdPrefix } from "./tour"
import type { TourChapter, TourDefinition, TourMemory } from "./tour"

/**
 * The short tours (D356), offered after the welcome's and from Preferences.
 *
 * Where there is something to do, the person does it on a practice database
 * the tour makes and takes away; where the point is only where things are —
 * dashboards, the agent — a chapter rings a control and waits for Next.
 */

const database = (memory: TourMemory) => memory.database ?? null

/** The practice connection's row in the connections column. */
function practiceRow(memory: TourMemory): string | null {
  const made = database(memory)
  return made ? testId(`connector-${made.name}`) : null
}

async function makePracticeDatabase(kit: Parameters<NonNullable<TourDefinition["setup"]>>[0]) {
  return rememberDatabase({}, await kit.makePractice())
}

// --- A table read in other ways ------------------------------------------

/** Each view opens a tab of its own: the next one starts from the table's. */
const backToTable = {
  locate: (memory: TourMemory) => {
    const made = database(memory)
    return made ? testIdPrefix(`workspace-tab-rows:${made.id}:`) : null
  },
  hint: say("onboarding.tours.views.back", { table: TOUR_TABLE }),
}

const viewsOpen: TourChapter = {
  id: "views-open",
  title: say("onboarding.tours.views.open.title"),
  targets: [
    { locate: practiceRow, hint: say("onboarding.tours.views.open.connection") },
    {
      locate: (memory) => {
        const made = database(memory)
        return made ? inCatalog(made.id, `catalog-node-${TOUR_TABLE}`) : null
      },
      hint: say("onboarding.tours.views.open.table", { table: TOUR_TABLE }),
    },
  ],
  done: {
    kind: "shown",
    locate: (memory) => {
      const made = database(memory)
      return made ? testIdPrefix(`workspace-tab-rows:${made.id}:`) : null
    },
  },
}

const viewsChart: TourChapter = {
  id: "views-chart",
  title: say("onboarding.tours.views.chart.title"),
  targets: [backToTable, { locate: () => testId("grid-charts"), hint: say("onboarding.tours.views.chart.hint") }],
  done: { kind: "shown", locate: () => testId("chart-panel") },
}

const viewsStructure: TourChapter = {
  id: "views-structure",
  title: say("onboarding.tours.views.structure.title"),
  targets: [backToTable, { locate: () => testId("grid-structure"), hint: say("onboarding.tours.views.structure.hint") }],
  done: {
    kind: "shown",
    locate: (memory) => {
      const made = database(memory)
      return made ? testIdPrefix(`workspace-tab-structure:${made.id}:`) : null
    },
  },
}

const viewsDocument: TourChapter = {
  id: "views-document",
  title: say("onboarding.tours.views.document.title"),
  targets: [backToTable, { locate: () => testId("grid-content"), hint: say("onboarding.tours.views.document.hint") }],
  done: {
    kind: "shown",
    locate: (memory) => {
      const made = database(memory)
      return made ? testIdPrefix(`workspace-tab-content:${made.id}:`) : null
    },
  },
}

export const VIEWS_TOUR: TourDefinition = {
  id: "views",
  title: say("onboarding.tours.views.title"),
  summary: say("onboarding.tours.views.summary"),
  chapters: [viewsOpen, viewsChart, viewsStructure, viewsDocument],
  setup: makePracticeDatabase,
  cleanup: async (kit, memory) => {
    if (memory.database) await kit.removeWithFile(memory.database.id)
  },
  closing: {
    title: say("onboarding.tours.views.closing.title"),
    text: say("onboarding.tours.views.closing.text"),
  },
}

// --- A pipeline from the practice database into the person's folder -------

/** A connection in the rail beside the canvas, where cards come from. */
const inRail = (name: string) => `${testId("pipelines-rail")} ${testId(`connector-${name}`)}`
const inPicker = (id: string) => `${testId("card-picker")} ${testId(id)}`
const onCanvas = `${testId("pipeline-canvas")} ${testIdPrefix("graph-node-")}`

const pipelineMade: TourChapter = {
  id: "pipeline-new",
  title: say("onboarding.tours.pipeline.new.title"),
  targets: [
    { locate: () => testId("space-pipelines"), hint: say("onboarding.tours.pipeline.new.space") },
    { locate: () => testId("pipeline-new"), hint: say("onboarding.tours.pipeline.new.create") },
    { locate: () => testId("pipeline-create-first"), hint: say("onboarding.tours.pipeline.new.create") },
  ],
  done: {
    kind: "mutation",
    key: createPipelineKey,
    settle: ({ data }, memory) =>
      isRecord(data) && typeof data.id === "string" ? { ...memory, pipeline: { id: data.id } } : null,
  },
}

const pipelineSource: TourChapter = {
  id: "pipeline-source",
  title: say("onboarding.tours.pipeline.source.title"),
  targets: [
    {
      locate: (memory) => (database(memory) ? inRail(database(memory)?.name ?? "") : null),
      hint: say("onboarding.tours.pipeline.source.connection"),
    },
    // SQLite's one schema is a level of its own in the picker (D248).
    { locate: () => inPicker("catalog-node-main"), hint: say("onboarding.tours.pipeline.source.schema") },
    { locate: () => inPicker(`catalog-check-${TOUR_TABLE}`), hint: say("onboarding.tours.pipeline.source.tick", { table: TOUR_TABLE }) },
    {
      locate: () => inPicker("card-picker-done"),
      hint: say("onboarding.tours.pipeline.source.done"),
      ready: (_, find) => find(`${inPicker(`catalog-check-${TOUR_TABLE}`)}[aria-checked="true"]`) !== null,
    },
  ],
  done: { kind: "shown", locate: () => onCanvas },
}

const pipelineTarget: TourChapter = {
  id: "pipeline-target",
  title: say("onboarding.tours.pipeline.target.title"),
  targets: [
    {
      locate: (memory) => (memory.folder ? inRail(memory.folder.name) : null),
      hint: say("onboarding.tours.pipeline.target.connection"),
    },
    { locate: () => inPicker("card-picker-top"), hint: say("onboarding.tours.pipeline.target.top") },
    {
      locate: () => inPicker("card-picker-done"),
      hint: say("onboarding.tours.pipeline.target.done"),
      ready: (_, find) => find(`${inPicker("card-picker-top")}[aria-checked="true"]`) !== null,
    },
  ],
  // Two cards: the practice database's and the folder's.
  done: { kind: "shown", locate: () => onCanvas, atLeast: 2 },
}

const pipelineLinked: TourChapter = {
  id: "pipeline-link",
  title: say("onboarding.tours.pipeline.link.title"),
  targets: [
    // The practice database's card came first, and the table is its row (D363).
    {
      locate: () => `${testId("pipeline-canvas")} [data-port-id^="node:"]`,
      hint: say("onboarding.tours.pipeline.link.hint", { table: TOUR_TABLE }),
    },
  ],
  done: { kind: "shown", locate: () => testId("link-panel") },
}

const pipelineRun: TourChapter = {
  id: "pipeline-run",
  title: say("onboarding.tours.pipeline.run.title"),
  targets: [
    { locate: () => testId("pipeline-run-menu"), hint: say("onboarding.tours.pipeline.run.menu") },
    { locate: () => testId("menu-item-run-once"), hint: say("onboarding.tours.pipeline.run.hint") },
    // A tour taken twice finds its file already there, and the link refuses.
    {
      locate: () => testId("link-panel-conflict"),
      hint: say("onboarding.tours.pipeline.run.taken"),
      ready: (_, find) => find(`${testId("link-panel-result")}[data-outcome="failed"]`) !== null,
    },
  ],
  done: { kind: "shown", locate: () => `${testId("link-panel-result")}[data-outcome="done"]` },
}

const inData = (_: TourMemory, find: (selector: string) => Element | null) =>
  find(testId("pipelines-space")) === null

const pipelineSeen: TourChapter = {
  id: "pipeline-seen",
  title: say("onboarding.tours.pipeline.seen.title"),
  targets: [
    { locate: () => testId("space-data"), hint: say("onboarding.tours.pipeline.seen.space") },
    // The pipelines' rail and picker carry the same rows: only Data's count.
    {
      locate: (memory) => (memory.folder ? testId(`connector-${memory.folder.name}`) : null),
      hint: say("onboarding.tours.pipeline.seen.folder"),
      ready: inData,
      // A long folder may not have the file's row drawn yet.
      enough: true,
    },
    {
      // Named after the table, numbered when the name was taken (D176).
      locate: () => `${testIdPrefix(`catalog-node-${TOUR_TABLE}`)}[data-testid$=".csv"]`,
      hint: say("onboarding.tours.pipeline.seen.file"),
      ready: inData,
    },
  ],
  done: { kind: "next" },
}

export const PIPELINE_TOUR: TourDefinition = {
  id: "pipeline",
  title: say("onboarding.tours.pipeline.title"),
  summary: say("onboarding.tours.pipeline.summary"),
  chapters: [pipelineMade, pipelineSource, pipelineTarget, pipelineLinked, pipelineRun, pipelineSeen],
  setup: async (kit) => {
    const memory = await makePracticeDatabase(kit)
    return { ...memory, folder: await kit.ensureFolder() }
  },
  // The CSV stays in the person's folder: it is what they made. The pipeline
  // goes with the database its first card reads.
  cleanup: async (kit, memory) => {
    if (memory.pipeline) await kit.removePipeline(memory.pipeline.id)
    if (memory.database) await kit.removeWithFile(memory.database.id)
  },
}

// --- Dashboards: where things are, nothing started ------------------------

export const DASHBOARDS_TOUR: TourDefinition = {
  id: "dashboards",
  title: say("onboarding.tours.dashboards.title"),
  summary: say("onboarding.tours.dashboards.summary"),
  chapters: [
    {
      id: "dashboards-space",
      title: say("onboarding.tours.dashboards.space.title"),
      targets: [{ locate: () => testId("space-dashboards"), hint: say("onboarding.tours.dashboards.space.hint") }],
      done: { kind: "shown", locate: () => testId("dashboards-space") },
    },
    {
      id: "dashboards-new",
      title: say("onboarding.tours.dashboards.new.title"),
      targets: [
        // Without a store an administrator starts one first (D126).
        { locate: () => testId("store-setup"), hint: say("onboarding.tours.dashboards.new.store"), enough: true },
        { locate: () => testId("dashboard-new"), hint: say("onboarding.tours.dashboards.new.hint"), enough: true },
        { locate: () => testId("dashboard-create-first"), hint: say("onboarding.tours.dashboards.new.hint") },
      ],
      done: { kind: "next" },
    },
    {
      id: "dashboards-agent",
      title: say("onboarding.tours.dashboards.agent.title"),
      targets: [
        { locate: () => testId("agents-open"), hint: say("onboarding.tours.dashboards.agent.open") },
        { locate: () => testId("agents-view-agents"), hint: say("onboarding.tours.dashboards.agent.view") },
        {
          locate: () => testId("agent-register-row"),
          hint: say("onboarding.tours.dashboards.agent.register"),
          ready: (_, find) => find(`${testId("agents-view-agents")}[aria-selected="true"]`) !== null,
        },
      ],
      done: { kind: "next" },
    },
    {
      id: "dashboards-connections",
      title: say("onboarding.tours.dashboards.connections.title"),
      targets: [
        { locate: () => testId("agents-view-connections"), hint: say("onboarding.tours.dashboards.connections.view") },
        {
          locate: () => testId("reporting-table"),
          hint: say("onboarding.tours.dashboards.connections.switch"),
          ready: (_, find) => find(`${testId("agents-view-connections")}[aria-selected="true"]`) !== null,
        },
      ],
      done: { kind: "next" },
    },
  ],
}

// --- The agent: where its key, model and context are chosen ---------------

export const AGENT_TOUR: TourDefinition = {
  id: "agent",
  title: say("onboarding.tours.agent.title"),
  summary: say("onboarding.tours.agent.summary"),
  chapters: [
    {
      id: "agent-space",
      title: say("onboarding.tours.agent.space.title"),
      targets: [{ locate: () => testId("space-ai"), hint: say("onboarding.tours.agent.space.hint") }],
      done: { kind: "shown", locate: () => testId("ai-new-chat") },
    },
    {
      // A chat's model field carries no key button; the default model's does.
      id: "agent-key",
      title: say("onboarding.tours.agent.key.title"),
      targets: [
        { locate: () => testId("ai-open-settings"), hint: say("onboarding.tours.agent.key.open") },
        {
          locate: () => testId("ai-selected-model-key"),
          hint: say("onboarding.tours.agent.key.hint"),
          ready: (_, find) => find(testId("ai-settings")) !== null,
        },
      ],
      done: { kind: "next" },
    },
    {
      id: "agent-chat",
      title: say("onboarding.tours.agent.chat.title"),
      targets: [
        { locate: () => testId("ai-new-chat"), hint: say("onboarding.tours.agent.chat.hint") },
        // The settings fill the space a chat would take.
        {
          locate: () => testId("ai-open-settings"),
          hint: say("onboarding.tours.agent.chat.close"),
          ready: (_, find) => find(testId("ai-settings")) !== null,
        },
      ],
      done: { kind: "shown", locate: () => testId("ai-composer") },
    },
    {
      id: "agent-model",
      title: say("onboarding.tours.agent.model.title"),
      targets: [{ locate: () => testId("ai-chat-model"), hint: say("onboarding.tours.agent.model.hint") }],
      done: { kind: "next" },
    },
    {
      id: "agent-attach",
      title: say("onboarding.tours.agent.attach.title"),
      targets: [{ locate: () => testId("ai-attach"), hint: say("onboarding.tours.agent.attach.hint") }],
      done: { kind: "next" },
    },
  ],
}

/** In the order Preferences lists them. */
export const SHORT_TOURS: readonly TourDefinition[] = [VIEWS_TOUR, PIPELINE_TOUR, DASHBOARDS_TOUR, AGENT_TOUR]
