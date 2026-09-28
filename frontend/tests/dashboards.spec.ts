import { createHash, createHmac, randomUUID } from "node:crypto"
import dgram from "node:dgram"

import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { toast } from "./utils/notices"
import { COLLEAGUE_PASSWORD, colleagueEmail, createColleague, removeColleague, signInAs } from "./utils/people"
import { openNode, pickSchema } from "./utils/catalog"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

/**
 * Dashboards (D125–D130). The agent scenarios need the metrics store set up on
 * the development stack and the metrics process listening on METRICS_UDP_PORT;
 * each registers an agent of its own and sends DPMA/1 datagrams itself, signed
 * the way dataplayer-monitor-agent signs them.
 */

const UDP_PORT = Number(process.env.METRICS_UDP_PORT ?? "9999")

/** Whether the dashboards open on a store, rather than on setting one up. */
async function storeIsReady(page: Page): Promise<boolean> {
  await page.getByTestId("space-dashboards").click()
  const rail = page.getByTestId("dashboards-rail")
  await expect(rail.or(page.getByTestId("store-setup"))).toBeVisible()
  return rail.isVisible()
}

function sendDatagram(datagram: Buffer): Promise<void> {
  return new Promise((resolve, reject) => {
    const socket = dgram.createSocket("udp4")
    socket.send(datagram, UDP_PORT, "127.0.0.1", (error) => {
      socket.close()
      if (error) reject(error)
      else resolve()
    })
  })
}

/** One agent process reporting one host: what every datagram's header names. */
interface AgentRun {
  key: string
  host: string
  instance: string
  started: number
  boot: string
  seq: number
}

function seconds(): number {
  return Math.floor(Date.now() / 1000)
}

function agentRun(key: string, host: string, started = seconds() - 600): AgentRun {
  return { key, host, instance: randomUUID(), started, boot: randomUUID(), seq: 0 }
}

async function report(run: AgentRun, time: number, kind: "metrics" | "processes" | "host", fields: object): Promise<void> {
  run.seq += 1
  const body = Buffer.from(JSON.stringify({
    v: 1,
    agent: { version: "0.1.1", instance: run.instance, started: run.started },
    host: { name: run.host, boot: run.boot },
    seq: run.seq,
    time,
    kind,
    ...fields,
  }))
  const kid = createHash("sha256").update(run.key).digest("hex").slice(0, 16)
  const signature = createHmac("sha256", run.key).update(body).digest("base64url")
  await sendDatagram(Buffer.concat([Buffer.from(`DPMA/1 ${kid} ${signature}\n`), body]))
}

interface MetricsApi {
  base: string
  headers: Record<string, string>
}

/** The metrics API, as the page is signed in to it. */
async function metricsApi(page: Page): Promise<MetricsApi> {
  const token = await page.evaluate(() => Object.entries(localStorage)
    .find(([key]) => key.endsWith("access_token"))?.[1])
  expect(token).toBeTruthy()
  const server = await page.evaluate(() => JSON.parse(
    sessionStorage.getItem("dataplayer:active-server:v1") ?? "null"
  ) as { url: string })
  return { base: `${server.url}/api/v1/metrics`, headers: { Authorization: `Bearer ${token ?? ""}` } }
}

interface ListedDashboard {
  id: string
  name: string
  color: string | null
  version: number
  options: object
}

async function listedDashboards(page: Page, api: MetricsApi): Promise<ListedDashboard[]> {
  const listed = await page.request.get(`${api.base}/dashboards`, { headers: api.headers })
  expect(listed.ok(), await listed.text()).toBe(true)
  return (await listed.json()) as ListedDashboard[]
}

/**
 * Puts a process table on a dashboard past the screen, so it is no longer
 * empty and New makes another (D129). A process table needs an agent, not a
 * store with series in it. Returns the agent, for the test to remove.
 */
async function fillDashboard(page: Page, name: string): Promise<string> {
  const api = await metricsApi(page)
  const agent = await page.request.post(`${api.base}/agents`, { headers: api.headers, data: { name: `${name}-agent` } })
  expect(agent.ok(), await agent.text()).toBe(true)
  const agentId = ((await agent.json()) as { agent: { id: string } }).agent.id
  const dashboard = (await listedDashboards(page, api)).find((one) => one.name === name)
  expect(dashboard).toBeDefined()
  if (dashboard === undefined) return agentId
  const saved = await page.request.put(`${api.base}/dashboards/${dashboard.id}`, {
    headers: api.headers,
    data: {
      name: dashboard.name,
      color: dashboard.color,
      version: dashboard.version,
      options: dashboard.options,
      widgets: [{
        type: "processes",
        id: randomUUID(),
        title: "Processes",
        layout: { x: 0, y: 0, w: 6, h: 6 },
        agent_id: agentId,
        host: "e2e-host",
      }],
    },
  })
  expect(saved.ok(), await saved.text()).toBe(true)
  return agentId
}

/** CPU busy share, load and uptime: three charts' and a tile's worth. */
function cpuSamples(uptime: number, busy = 10): { samples: unknown[][] } {
  return {
    samples: [
      ["cpu", "utilization", "total", "%", busy],
      ["cpu", "utilization", "cpu0", "%", busy / 2],
      ["cpu", "load1", "", "", 0.1],
      ["cpu", "load5", "", "", 0.2],
      ["cpu", "load15", "", "", 0.3],
      ["host", "uptime", "", "s", uptime],
    ],
  }
}

test("the dashboards cover the workspace, which is still where it was on the way back", async ({ page }) => {
  const name = `e2e-space-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await page.getByTestId("grid-next").click()
  await expect(page.getByTestId("grid-page-range")).not.toHaveText("Rows 0")
  const range = await page.getByTestId("grid-page-range").innerText()

  await page.getByTestId("space-dashboards").click()
  await expect(page.getByTestId("dashboards-space")).toBeVisible()
  await expect(page.getByTestId("grid-page-range")).toHaveCount(0)
  await expect(page.getByTestId("space-dashboards")).toHaveAttribute("aria-pressed", "true")

  // The grid was parked, not rebuilt: the same page, not the first one again.
  await page.getByTestId("space-data").click()
  await expect(page.getByTestId("dashboards-space")).toHaveCount(0)
  await expect(page.getByTestId("grid-page-range")).toHaveText(range)

  // Which space is shown is remembered across a reload, like the layout.
  await page.getByTestId("space-dashboards").click()
  await page.reload()
  await expect(page.getByTestId("dashboards-space")).toBeVisible()
  await page.getByTestId("space-data").click()
  await expect(page.getByTestId("grid-page-range")).toBeVisible()

  // Opening something from the dashboards' side brings the data back: the
  // query library stands under every space, and a console opened from it
  // belongs to Data (D143).
  await page.getByTestId("space-dashboards").click()
  await page.getByTestId("command-queries").click()
  await expect(page.getByTestId("dashboards-space")).toBeVisible()
  await page.getByTestId("new-query").click()
  await expect(page.getByTestId("dashboards-space")).toHaveCount(0)
  await page.getByTestId("command-queries").click()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("a superuser starts the metrics store from the dashboards", async ({ page }) => {
  // Once per stack: a store that is there already is the ordinary case.
  test.setTimeout(240_000)
  await login(page)
  test.skip(await storeIsReady(page), "The metrics store is already set up")
  const start = page.getByTestId("store-start")
  test.skip(!(await start.isEnabled()), "This stack cannot start services")

  await start.click()
  await expect(page.getByTestId("store-progress")).toBeVisible()
  await expect(page.getByTestId("dashboards-rail")).toBeVisible({ timeout: 200_000 })
})

test("a host's ready-made layout shows its processes, takes live points and opens a widget in a window", async ({ page }) => {
  test.setTimeout(90_000)
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const stamp = Date.now()
  const agentName = `e2e-agent-${stamp}`
  const host = `e2e-host-${stamp}`
  const dashboardName = `e2e-dashboard-${stamp}`

  await page.getByTestId("agents-open").click()
  await page.getByTestId("agent-name").fill(agentName)
  await page.getByTestId("agent-register").click()
  const key = (await page.getByTestId("agent-key").innerText()).trim()
  await page.getByTestId("agents-dialog").getByRole("button", { name: "Close", exact: true }).click()
  await page.waitForTimeout(1500)

  const run = agentRun(key, host)
  const now = seconds()
  for (const offset of [90, 60, 30]) await report(run, now - offset, "metrics", cpuSamples(5000 - offset))
  await report(run, now, "processes", {
    total: 212,
    part: [1, 1],
    rows: [[4242, 1, "root", "R", 7.5, 1.0, 104857600, now - 600, "e2e-worker", "e2e-worker --serve"]],
  })

  await page.getByTestId("dashboard-new").click()
  await page.getByRole("button", { name: "Rename this dashboard" }).click()
  await page.getByTestId("dashboard-rename-input").fill(dashboardName)
  await page.getByTestId("dashboard-rename-input").press("Enter")
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toBeVisible()
  // Off, so what changes on screen below can only have come through the socket.
  await page.getByTestId("dashboard-refresh").click()
  await page.getByRole("option", { name: "Off", exact: true }).click()

  await expect(async () => {
    await page.reload()
    await page.getByTestId("dashboard-add").click()
    await expect(page.getByTestId("add-widgets-tree").getByText(agentName, { exact: true })).toBeVisible({ timeout: 2000 })
  }).toPass({ timeout: 30_000 })

  // Every source starts shut, and its name opens it.
  const hostRow = page.getByTestId("add-widgets-tree").getByText(host, { exact: true })
  await expect(hostRow).toBeHidden()
  await page.getByTestId("add-widgets-tree").getByText(agentName, { exact: true }).click()
  await hostRow.click()
  await expect(page.getByTestId("add-widgets-presets")).toContainText("Linux host for")
  // A host that reports its CPU, uptime and processes fills four recipes:
  // per core, load, uptime and the process table.
  await expect(page.getByTestId("add-widgets-presets")).toContainText("4 of 13 widgets")
  await page.getByTestId("add-preset-linux-host").click()

  await expect(page.getByTestId("widget")).toHaveCount(4)
  await expect(page.getByTestId("processes-widget")).toContainText("e2e-worker --serve")
  await expect(page.getByTestId("processes-widget")).toContainText("212 processes on the host")
  await expect(page.getByTestId("processes-widget")).toContainText("100 MB")
  const uptime = page.getByTestId("stat-value")
  await expect(uptime).toHaveText("1 h 22 min")

  await report(run, seconds(), "metrics", cpuSamples(5000 + 180))
  await expect(uptime).toHaveText("1 h 26 min", { timeout: 15_000 })

  const tile = page.getByTestId("widget").filter({ has: page.getByTestId("stat-value") })
  await tile.getByTestId("widget-detach").click()
  const floating = page.getByRole("dialog", { name: "Uptime", exact: true })
  await expect(floating.getByTestId("stat-value")).toHaveText("1 h 26 min")
  await page.getByTestId("space-data").click()
  await expect(floating).toBeVisible()
  await floating.getByRole("button", { name: "Close window" }).click()
  await expect(floating).toHaveCount(0)

  await page.getByTestId("space-dashboards").click()
  await page.getByTestId(`dashboard-${dashboardName}`).click()
  await page.getByRole("button", { name: "Delete this dashboard" }).click()
  await page.getByTestId("confirm-accept").click()
  await page.getByTestId("agents-open").click()
  const row = page.getByTestId("agents-table").getByRole("row", { name: new RegExp(agentName) })
  await row.getByRole("button", { name: "Remove this agent" }).click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("agents-table").getByText(agentName)).toHaveCount(0)
})

test("a connection's owner switches its reporting on and its layout is drawn from what it reports", async ({ page }) => {
  test.setTimeout(120_000)
  const stamp = Date.now()
  const name = `e2e-reporting-${stamp}`
  const dashboardName = `e2e-dashboard-${stamp}`
  await login(page)
  await createPostgresConnector(page, name)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")

  await page.getByTestId("agents-open").click()
  const sources = page.getByTestId("agents-dialog")
  // Agents come first; connections are the other view of the same window.
  await expect(sources.getByTestId("reporting-table")).toHaveCount(0)
  await sources.getByTestId("agents-view-connections").click()
  const row = sources.getByTestId("reporting-table").getByRole("row", { name: new RegExp(name) })
  await expect(row).toBeVisible()
  await row.getByTestId(`reporting-${name}`).click()
  await row.getByRole("combobox", { name: "How often" }).click()
  await page.getByRole("option", { name: "Every 15 s", exact: true }).click()
  await expect(row.getByTestId(`reporting-${name}`)).toHaveAttribute("aria-checked", "true")
  await sources.getByRole("button", { name: "Close", exact: true }).click()

  await page.getByTestId("dashboard-new").click()
  await page.getByRole("button", { name: "Rename this dashboard" }).click()
  await page.getByTestId("dashboard-rename-input").fill(dashboardName)
  await page.getByTestId("dashboard-rename-input").press("Enter")
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toBeVisible()

  // Polled within a few seconds; the rates need a second poll, fifteen later.
  await page.waitForTimeout(20_000)
  await expect(async () => {
    await page.reload()
    await page.getByTestId("dashboard-add").click()
    await expect(page.getByTestId("add-widgets-tree").getByText(name, { exact: true })).toBeVisible({ timeout: 2000 })
  }).toPass({ timeout: 45_000 })

  await page.getByTestId("add-widgets-tree").getByText(name, { exact: true }).click()
  await expect(page.getByTestId("add-widgets-presets")).toContainText(`PostgreSQL database for ${name}`)
  await page.getByTestId("add-preset-postgres-database").click()

  await expect(page.getByTestId("widget").filter({ hasText: "Sessions by state" })).toBeVisible()
  await expect(page.getByTestId("widget").filter({ hasText: "Database size" }).getByTestId("stat-value")).toHaveText(/\d+(\.\d+)? (KB|MB|GB)/)
  await expect(page.getByTestId("widget").filter({ hasText: "Transactions per second" }).getByTestId("series-chart")).toBeVisible()

  await page.getByRole("button", { name: "Delete this dashboard" }).click()
  await page.getByTestId("confirm-accept").click()
  await page.getByTestId("space-data").click()
  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("an agent's datagrams describe its host and become a dashboard of widgets", async ({ page }) => {
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const agentName = `e2e-agent-${Date.now()}`
  const host = `e2e-host-${Date.now()}`

  await page.getByTestId("agents-open").click()
  await page.getByTestId("agent-name").fill(agentName)
  await page.getByTestId("agent-register").click()
  const key = (await page.getByTestId("agent-key").innerText()).trim()
  expect(key.length).toBeGreaterThanOrEqual(32)
  await expect(page.getByTestId("agent-snippet")).toContainText(`DPM_KEY: "${key}"`)
  await expect(page.getByTestId("agent-snippet")).toContainText("image: alaramus/dataplayer-monitor-agent:latest")

  // The metrics process reads keys again on an unknown id at most once a
  // second; a datagram later than that is accepted whenever the keys were read.
  await page.waitForTimeout(1500)
  const run = agentRun(key, host)
  const now = seconds()
  for (const offset of [120, 90, 60, 30, 0]) {
    await report(run, now - offset, "metrics", cpuSamples(5000 - offset, 10 + offset / 10))
  }
  await report(run, now, "host", {
    info: {
      os: "Ubuntu 24.04.1 LTS", kernel: "6.8.0-45-generic", arch: "amd64", cpus: 8, cpu_model: "Intel(R) Xeon(R)",
      memory: 16 * 1024 ** 3, boot_time: now - 5000, collectors: { cpu: 15, processes: 60 },
    },
  })

  // What the host is, in the same window, once the datagram is written.
  const hosts = page.getByTestId("hosts-table")
  await expect(async () => {
    await page.getByTestId("agents-dialog").getByRole("button", { name: "Close", exact: true }).click()
    await page.getByTestId("agents-open").click()
    await expect(hosts.getByRole("row", { name: new RegExp(host) })).toContainText("8 CPUs · 16 GB", { timeout: 2000 })
  }).toPass({ timeout: 30_000 })
  const described = hosts.getByRole("row", { name: new RegExp(host) })
  await expect(described).toContainText("Ubuntu 24.04.1 LTS · amd64")
  await expect(described).toContainText(agentName)
  await described.getByText(host, { exact: true }).hover()
  await expect(page.getByRole("tooltip")).toContainText("Agent 0.1.1, kernel 6.8.0-45-generic")
  await expect(described).toContainText("1 h 23 min")
  await page.getByTestId("agents-dialog").getByRole("button", { name: "Close", exact: true }).click()

  const dashboardName = `e2e-dashboard-${Date.now()}`
  await page.getByTestId("dashboard-new").click()
  await expect(page.getByTestId("dashboard-view")).toBeVisible()
  await page.getByRole("button", { name: "Rename this dashboard" }).click()
  await page.getByTestId("dashboard-rename-input").fill(dashboardName)
  await page.getByTestId("dashboard-rename-input").press("Enter")
  await expect(page.getByTestId("dashboard-name")).toHaveText(dashboardName)
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toBeVisible()

  await page.getByTestId("dashboards-filter-open").click()
  const dashboardFilter = page.getByTestId("dashboards-name-filter")
  await expect(dashboardFilter).toBeFocused()
  await expect(page.getByTestId("dashboard-new")).toHaveCount(0)
  await dashboardFilter.fill(dashboardName.toUpperCase())
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toBeVisible()
  await dashboardFilter.fill("no dashboard has this name")
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toHaveCount(0)
  await expect(page.getByTestId("dashboards-rail")).toContainText("No matching dashboards")
  await dashboardFilter.press("Escape")
  await expect(page.getByTestId("dashboard-new")).toBeVisible()
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toBeVisible()

  // Written in batches of a second; the catalog is read again when asked.
  await expect(async () => {
    await page.reload()
    await page.getByTestId("dashboard-add").click()
    await page.getByTestId("add-widgets-tree").getByText(agentName, { exact: true }).click({ timeout: 2000 })
    await expect(page.getByTestId("add-widgets-tree").getByText(host, { exact: true })).toBeVisible({ timeout: 2000 })
  }).toPass({ timeout: 30_000 })

  const tree = page.getByTestId("add-widgets-tree")
  await tree.getByText(host, { exact: true }).locator("xpath=../..").getByRole("checkbox").click()
  // Uptime is a tile; the percentages and the unitless load are two charts,
  // because an axis has one scale.
  await expect(page.getByTestId("add-widgets")).toContainText("3 widgets")
  await page.getByTestId("add-widgets-confirm").click()

  const widgets = page.getByTestId("widget")
  await expect(widgets).toHaveCount(3)
  await expect(page.getByTestId("series-chart")).toHaveCount(2)
  await expect(page.getByTestId("stat-value")).toHaveText("1 h 23 min")

  // Saved a moment after the last change, and there after a reload.
  await page.waitForTimeout(1500)
  await page.reload()
  await page.getByTestId(`dashboard-${dashboardName}`).click()
  await expect(page.getByTestId("widget")).toHaveCount(3)

  await page.getByTestId("widget-remove").first().click()
  await expect(page.getByTestId("widget")).toHaveCount(2)

  await page.getByRole("button", { name: "Delete this dashboard" }).click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toHaveCount(0)

  await page.getByTestId("agents-open").click()
  const row = page.getByTestId("agents-table").getByRole("row", { name: new RegExp(agentName) })
  await row.getByRole("button", { name: "Remove this agent" }).click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("agents-table").getByText(agentName)).toHaveCount(0)
})

test("a host whose agent keeps starting again needs its owner", async ({ page }) => {
  test.setTimeout(90_000)
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const stamp = Date.now()
  const agentName = `e2e-restarting-${stamp}`
  const host = `e2e-crashing-${stamp}`

  await page.getByTestId("agents-open").click()
  await page.getByTestId("agent-name").fill(agentName)
  await page.getByTestId("agent-register").click()
  const key = (await page.getByTestId("agent-key").innerText()).trim()
  await page.getByTestId("agents-dialog").getByRole("button", { name: "Close", exact: true }).click()
  await page.waitForTimeout(1500)

  // An agent that crashes a couple of seconds after it starts, four times: a
  // new process on the same boot each time, the first known, three restarts.
  const now = seconds()
  const boot = randomUUID()
  for (const ago of [102, 68, 34, 0]) {
    const run = { ...agentRun(key, host, now - ago - 2), boot }
    await report(run, now - ago, "metrics", cpuSamples(5000 - ago))
  }

  const item = page.getByTestId("attention-section").getByText(`${host} keeps restarting`)
  await expect(async () => {
    await page.reload()
    await page.getByTestId("activity-indicator").click()
    await expect(item).toBeVisible({ timeout: 2000 })
  }).toPass({ timeout: 30_000 })
  const row = page.locator("[data-testid^='attention-restarts:']").filter({ hasText: host })
  await expect(row).toContainText(`The agent ${agentName} started again 3 times in the last 15 minutes`)

  // From the data workspace, where the sheet is opened most of the time.
  await page.keyboard.press("Escape")
  await expect(page.getByTestId("activity-panel")).toHaveCount(0)
  await page.getByTestId("space-data").click()
  await expect(page.getByTestId("dashboards-space")).toHaveCount(0)
  await page.getByTestId("activity-indicator").click()
  await row.getByRole("button", { name: "Open Dashboards" }).click()
  await expect(page.getByTestId("dashboards-space")).toBeVisible()

  // An agent that is gone is nobody's to look after.
  await page.getByTestId("agents-open").click()
  const agent = page.getByTestId("agents-table").getByRole("row", { name: new RegExp(agentName) })
  await agent.getByRole("button", { name: "Remove this agent" }).click()
  await page.getByTestId("confirm-accept").click()
  await expect(async () => {
    await page.reload()
    await page.getByTestId("activity-indicator").click()
    await expect(page.getByTestId("activity-panel")).toBeVisible()
    await expect(item).toHaveCount(0, { timeout: 1000 })
  }).toPass({ timeout: 20_000 })
})

test("the rail is dragged wider and narrower by the gap beside it, never past two fifths, and keeps its width", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const space = page.getByTestId("dashboards-space")
  const rail = page.getByTestId("dashboards-rail")
  const gap = space.getByTestId("workspace-separator")
  const widthOf = async () => Math.round((await rail.boundingBox())?.width ?? 0)
  const spaceWidth = Math.round((await space.boundingBox())?.width ?? 0)

  const drag = async (dx: number) => {
    const box = await gap.boundingBox()
    if (box === null) throw new Error("The gap beside the rail is not drawn")
    const x = box.x + box.width / 2
    const y = box.y + box.height / 2
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x + dx / 2, y, { steps: 5 })
    await page.mouse.move(x + dx, y, { steps: 5 })
    await page.mouse.up()
  }

  await drag(-2000)
  const narrowest = await widthOf()
  await drag(100)
  expect(await widthOf()).toBe(narrowest + 100)

  await drag(2000)
  const widest = await widthOf()
  expect(widest).toBeLessThanOrEqual(Math.floor(spaceWidth * 0.4))
  expect(widest).toBeGreaterThan(Math.floor(spaceWidth * 0.4) - 5)

  await drag(-150)
  const chosen = await widthOf()
  await page.reload()
  await expect(rail).toBeVisible()
  expect(await widthOf()).toBe(chosen)
})

test("a long dashboard name keeps to one line of the rail, and says itself whole on hover", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const name = `e2e-long-name-${String(Date.now())}-${"x".repeat(60)}`
  await page.getByTestId("dashboard-new").click()
  await page.getByRole("button", { name: "Rename this dashboard" }).click()
  await page.getByTestId("dashboard-rename-input").fill(name)
  await page.getByTestId("dashboard-rename-input").press("Enter")
  const entry = page.getByTestId(`dashboard-${name}`)
  await expect(entry).toBeVisible()
  // Enter closes the window; it once reopened it through the pencil.
  await expect(page.getByRole("dialog", { name: "Rename dashboard" })).toHaveCount(0)

  // Wrapped, the name went under its icon over two or three lines.
  const railBox = await page.getByTestId("dashboards-rail").boundingBox()
  const entryBox = await entry.boundingBox()
  expect(entryBox!.height).toBeLessThan(40)
  expect(entryBox!.x + entryBox!.width).toBeLessThanOrEqual(railBox!.x + railBox!.width)
  await entry.hover()
  await expect(entry).toHaveAttribute("title", name)

  await entry.click()
  await page.getByRole("button", { name: "Delete this dashboard" }).click()
  await page.getByTestId("confirm-accept").click()
  await expect(entry).toHaveCount(0)
})

test("the rail is pushed aside to its icons and brought back by the header button or its gap, and stays as it was left", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const rail = page.getByTestId("dashboards-rail")
  const wide = Math.round((await rail.boundingBox())?.width ?? 0)
  const dashboardName = `e2e-narrow-${Date.now()}`
  await page.getByTestId("dashboard-new").click()
  await page.getByRole("button", { name: "Rename this dashboard" }).click()
  await page.getByTestId("dashboard-rename-input").fill(dashboardName)
  await page.getByTestId("dashboard-rename-input").press("Enter")
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toBeVisible()
  const colorOf = (testId: string) => page.getByTestId(testId).evaluate((element) => getComputedStyle(element).color)
  const openColor = await colorOf(`dashboard-${dashboardName}`)

  await page.getByTestId("app-toggle-first-panel").click()
  await expect(page.getByTestId("dashboards-rail-narrow")).toBeVisible()
  expect(Math.round((await rail.boundingBox())?.width ?? 0)).toBe(40)
  // The plus alone in a head of its own, on the strip the open dashboard's
  // head stands on.
  const railHead = page.getByTestId("dashboards-rail-head")
  const viewHead = page.getByTestId("dashboard-head")
  await expect(railHead.getByRole("button")).toHaveCount(1)
  await expect(railHead.getByTestId("dashboard-new")).toBeVisible()
  await expect(railHead).toHaveCSS(
    "background-color",
    await viewHead.evaluate((element) => getComputedStyle(element).backgroundColor)
  )
  const bottomOf = async (testId: string) => {
    const box = await page.getByTestId(testId).boundingBox()
    return Math.round((box?.y ?? 0) + (box?.height ?? 0))
  }
  expect(await bottomOf("dashboards-rail-head")).toBe(await bottomOf("dashboard-head"))
  // What the wide rail offers is still there, as icons, and the open
  // dashboard is marked in the same blue.
  await expect(page.getByTestId(`dashboard-narrow-${dashboardName}`)).toBeVisible()
  expect(await colorOf(`dashboard-narrow-${dashboardName}`)).toBe(openColor)
  expect(await colorOf("agents-open")).not.toBe(openColor)
  await expect(page.getByTestId("agents-open")).toBeVisible()
  await page.reload()
  await expect(page.getByTestId("dashboards-rail-narrow")).toBeVisible()

  await page.getByTestId("app-toggle-first-panel").click()
  await expect(page.getByTestId("dashboards-rail-narrow")).toHaveCount(0)
  expect(Math.round((await rail.boundingBox())?.width ?? 0)).toBe(wide)

  // A press on the gap beside the narrow rail brings it back too.
  await page.getByTestId("app-toggle-first-panel").click()
  await page.getByTestId("dashboards-space").getByTestId("workspace-separator").click()
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toBeVisible()

  await page.getByTestId(`dashboard-${dashboardName}`).click()
  await page.getByRole("button", { name: "Delete this dashboard" }).click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toHaveCount(0)
})

test("a dashboard takes a colour of its own, which the rail and its name carry, wide and narrow", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const stamp = Date.now()
  const coloured = `e2e-coloured-${stamp}`
  const plain = `e2e-plain-${stamp}`
  const create = async (name: string) => {
    await page.getByTestId("dashboard-new").click()
    await page.getByRole("button", { name: "Rename this dashboard" }).click()
    await page.getByTestId("dashboard-rename-input").fill(name)
    await page.getByTestId("dashboard-rename-input").press("Enter")
    await expect(page.getByTestId(`dashboard-${name}`)).toBeVisible()
  }
  const blue = "rgb(36, 106, 188)"

  await create(coloured)
  await page.getByTestId("dashboard-color").click()
  const picker = page.getByRole("dialog", { name: "Dashboard color", exact: true })
  await picker.getByRole("textbox").fill("#246abc")
  await page.keyboard.press("Escape")
  await expect(picker).toBeHidden()
  await expect(page.getByTestId("dashboard-name")).toHaveCSS("background-color", blue)
  await expect(page.getByTestId("dashboard-name")).toHaveCSS("color", "rgb(255, 255, 255)")
  // Open, the rail fills its entry with it, once the save has gone.
  await expect(page.getByTestId(`dashboard-${coloured}`)).toHaveCSS("background-color", blue, { timeout: 5000 })
  const agentId = await fillDashboard(page, coloured)

  await page.reload()
  await page.getByTestId(`dashboard-${coloured}`).click()
  await expect(page.getByTestId("dashboard-name")).toHaveCSS("background-color", blue)

  // Another open, the coloured one is washed in its colour instead.
  await create(plain)
  await expect(page.getByTestId(`dashboard-${coloured}`)).toHaveCSS("background-color", "rgba(36, 106, 188, 0.28)")
  await expect(page.getByTestId("dashboard-name")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)")

  await page.getByTestId("app-toggle-first-panel").click()
  await expect(page.getByTestId(`dashboard-narrow-${coloured}`).locator("xpath=..")).toHaveCSS("background-color", "rgba(36, 106, 188, 0.28)")
  await page.getByTestId(`dashboard-narrow-${coloured}`).click()
  await expect(page.getByTestId(`dashboard-narrow-${coloured}`).locator("xpath=..")).toHaveCSS("background-color", blue)
  await page.getByTestId("app-toggle-first-panel").click()

  // Reset, it is an ordinary dashboard again.
  await page.getByTestId("dashboard-color").click()
  await picker.getByRole("button", { name: "Reset color", exact: true }).click()
  await expect(page.getByTestId("dashboard-name")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)")
  await expect(page.getByTestId(`dashboard-${coloured}`)).toHaveCSS("background-color", "rgba(0, 0, 0, 0)", { timeout: 5000 })

  for (const name of [coloured, plain]) {
    await page.getByTestId(`dashboard-${name}`).click()
    await page.getByRole("button", { name: "Delete this dashboard" }).click()
    await page.getByTestId("confirm-accept").click()
    await expect(page.getByTestId(`dashboard-${name}`)).toHaveCount(0)
  }
  const api = await metricsApi(page)
  await page.request.delete(`${api.base}/agents/${agentId}`, { headers: api.headers })
})

test("New opens the empty dashboard the person already has rather than making another", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const api = await metricsApi(page)

  await page.getByTestId("dashboard-new").click()
  await expect(page.getByTestId("dashboard-view")).toBeVisible()
  const name = (await page.getByTestId("dashboard-name").innerText()).trim()
  const before = (await listedDashboards(page, api)).length

  await page.getByTestId("dashboard-new").click()

  await expect(toast(page, `"${name}" is still empty`).first()).toBeVisible()
  await expect(page.getByTestId("dashboard-name")).toHaveText(name)
  expect((await listedDashboards(page, api)).length).toBe(before)

  await page.getByRole("button", { name: "Delete this dashboard" }).click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId(`dashboard-${name}`)).toHaveCount(0)
})

test("the sources fold at the foot of the rail and open to half of it, and Sources is in its head", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const rail = page.getByTestId("dashboards-rail")
  const toggle = page.getByTestId("dashboards-sources-toggle")
  const lists = page.getByTestId("dashboards-lists")
  const box = async (locator: typeof rail) => {
    const found = await locator.boundingBox()
    if (found === null) throw new Error("no box")
    return found
  }

  // In the head now, beside the plus, not above the tree.
  const head = await box(page.getByTestId("dashboard-new"))
  expect(Math.abs((await box(page.getByTestId("agents-open"))).y - head.y)).toBeLessThan(2)

  // Folded, the dashboards reach down to the line of the sources at the foot.
  await expect(toggle).toHaveAttribute("aria-expanded", "false")
  await expect(page.getByTestId("dashboards-sources")).toHaveCount(0)
  const railBox = await box(rail)
  const folded = await box(toggle)
  expect(Math.abs(folded.y + folded.height - (railBox.y + railBox.height))).toBeLessThan(3)
  const listsBox = await box(lists)
  expect(Math.abs(listsBox.y + listsBox.height - folded.y)).toBeLessThan(2)

  // Open, the sources take the lower half, and stay open across a reload.
  await toggle.click()
  await expect(toggle).toHaveAttribute("aria-expanded", "true")
  await expect(page.getByTestId("dashboards-sources")).toBeVisible()
  expect(Math.abs((await box(toggle)).y - (railBox.y + railBox.height / 2))).toBeLessThan(railBox.height * 0.05)
  await page.reload()
  await expect(page.getByTestId("dashboards-sources-toggle")).toHaveAttribute("aria-expanded", "true")

  await page.getByTestId("dashboards-sources-toggle").click()
  await expect(page.getByTestId("dashboards-sources")).toHaveCount(0)
})

test("a superuser reads what the metrics store keeps, and is warned before removing it", async ({ page }) => {
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")

  await page.getByTestId("store-open").click()
  const dialog = page.getByTestId("store-dialog")
  await expect(dialog.getByTestId("store-size")).toContainText("series")
  await expect(dialog).toContainText("Samples as they came: kept 7 d")
  await expect(dialog).toContainText("Averages over 5 min: kept 35 d")
  await expect(dialog).toContainText("Averages over 1 h: kept 400 d")

  // Not taken further: removing the store takes every sample of the stack the
  // suite runs on. What removal does is the backend suite's to prove.
  await dialog.getByTestId("store-remove").click()
  await expect(page.getByTestId("confirm-message")).toContainText("every sample of every person")
  await page.getByTestId("confirm-cancel").click()
  await expect(dialog.getByTestId("store-origin")).toBeVisible()
  await dialog.getByRole("button", { name: "Close", exact: true }).click()
  await expect(page.getByTestId("dashboards-rail")).toBeVisible()
})

test("a dashboard shared with a colleague opens from its link, is edited once allowed, and goes when taken back", async ({ page, browser }) => {
  test.setTimeout(150_000)
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const stamp = Date.now()
  const email = colleagueEmail()
  const agentName = `e2e-shared-agent-${stamp}`
  const host = `e2e-shared-host-${stamp}`
  const dashboardName = `e2e-shared-${stamp}`

  await createColleague(page, email)
  await page.getByTestId("space-dashboards").click()
  await page.getByTestId("agents-open").click()
  await page.getByTestId("agent-name").fill(agentName)
  await page.getByTestId("agent-register").click()
  const key = (await page.getByTestId("agent-key").innerText()).trim()
  await page.getByTestId("agents-dialog").getByRole("button", { name: "Close", exact: true }).click()
  await page.waitForTimeout(1500)
  const run = agentRun(key, host)
  const now = seconds()
  for (const offset of [90, 60, 30, 0]) await report(run, now - offset, "metrics", cpuSamples(5000 - offset))

  await page.getByTestId("dashboard-new").click()
  await page.getByRole("button", { name: "Rename this dashboard" }).click()
  await page.getByTestId("dashboard-rename-input").fill(dashboardName)
  await page.getByTestId("dashboard-rename-input").press("Enter")
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toBeVisible()
  await expect(async () => {
    await page.reload()
    await page.getByTestId(`dashboard-${dashboardName}`).click()
    await page.getByTestId("dashboard-add").click()
    await page.getByTestId("add-widgets-tree").getByText(agentName, { exact: true }).click({ timeout: 2000 })
    await expect(page.getByTestId("add-widgets-tree").getByText(host, { exact: true })).toBeVisible({ timeout: 2000 })
  }).toPass({ timeout: 30_000 })
  await page.getByTestId("add-widgets-tree").getByText(host, { exact: true }).locator("xpath=../..").getByRole("checkbox").click()
  await page.getByTestId("add-widgets-confirm").click()
  await expect(page.getByTestId("widget")).toHaveCount(3)
  await page.waitForTimeout(1500)

  // --- the owner gives a colleague a look, and says what that includes -----
  await page.getByTestId("dashboard-share").click()
  const dialog = page.getByTestId("dashboard-share-dialog")
  await expect(dialog.getByTestId("dashboard-share-warning")).toContainText("your agents' hosts included")
  const link = await dialog.getByTestId("dashboard-share-link").inputValue()
  expect(link).toContain("/dashboards/")
  await dialog.getByTestId("dashboard-share-user").click()
  await page.getByRole("option", { name: email }).click()
  await dialog.getByTestId("dashboard-share-submit").click()
  await expect(dialog.getByTestId(`dashboard-grant-${email}`)).toContainText("Can view")
  await dialog.getByRole("button", { name: "Close", exact: true }).click()

  const url = new URL(link)
  const theirs = await browser.newContext({ baseURL: url.origin })
  const colleague = await theirs.newPage()
  try {
    await signInAs(colleague, email, COLLEAGUE_PASSWORD)
    await colleague.goto(url.pathname)
    await expect(colleague.getByTestId("dashboard-name")).toHaveText(dashboardName)
    await expect(colleague.getByTestId("dashboard-shared-by")).toContainText("View only")
    // The agent is not theirs: the tile reads it through the dashboard.
    await expect(colleague.getByTestId("stat-value")).toHaveText("1 h 23 min")
    await expect(colleague.getByTestId("dashboard-add")).toHaveCount(0)
    await expect(colleague.getByTestId("widget-remove")).toHaveCount(0)
    await expect(colleague.getByTestId("dashboards-shared")).toContainText(dashboardName)

    // --- allowed to edit, the colleague can add ----------------------------
    await page.getByTestId("dashboard-share").click()
    await dialog.getByTestId(`dashboard-grant-level-${email}`).click()
    await page.getByRole("option", { name: "Can edit", exact: true }).click()
    await expect(dialog.getByTestId(`dashboard-grant-${email}`)).toContainText("Can edit")
    await colleague.reload()
    await colleague.getByTestId(`dashboard-${dashboardName}`).click()
    await expect(colleague.getByTestId("dashboard-add")).toBeVisible()
    await expect(colleague.getByTestId("dashboard-shared-by")).toContainText("You can edit")

    // --- taken back, it is gone, and its link says only that --------------
    await dialog.getByTestId(`dashboard-grant-revoke-${email}`).click()
    await expect(dialog.getByTestId(`dashboard-grant-${email}`)).toHaveCount(0)
    await dialog.getByRole("button", { name: "Close", exact: true }).click()
    await colleague.reload()
    await expect(colleague.getByTestId(`dashboard-${dashboardName}`)).toHaveCount(0)
    await colleague.goto(url.pathname)
    await expect(colleague.getByText("That dashboard does not exist, or it has not been shared with you")).toBeVisible()
  } finally {
    await theirs.close()
  }

  await page.getByRole("button", { name: "Delete this dashboard" }).click()
  await page.getByTestId("confirm-accept").click()
  await page.getByTestId("agents-open").click()
  const row = page.getByTestId("agents-table").getByRole("row", { name: new RegExp(agentName) })
  await row.getByRole("button", { name: "Remove this agent" }).click()
  await page.getByTestId("confirm-accept").click()
  await page.getByTestId("agents-dialog").getByRole("button", { name: "Close", exact: true }).click()
  await removeColleague(page, email)
})
