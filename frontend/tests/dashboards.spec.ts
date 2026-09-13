import dgram from "node:dgram"

import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { openNode, pickSchema } from "./utils/catalog"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

/**
 * Dashboards (D125–D130). The last scenario needs the metrics store set up on
 * the development stack and the metrics process listening on METRICS_UDP_PORT;
 * it registers an agent of its own and sends the packets itself.
 */

const UDP_PORT = Number(process.env.METRICS_UDP_PORT ?? "9999")

/** Whether the dashboards open on a store, rather than on setting one up. */
async function storeIsReady(page: Page): Promise<boolean> {
  await page.getByTestId("space-dashboards").click()
  const rail = page.getByTestId("dashboards-rail")
  await expect(rail.or(page.getByTestId("store-setup"))).toBeVisible()
  return rail.isVisible()
}

function send(packet: object): Promise<void> {
  return new Promise((resolve, reject) => {
    const socket = dgram.createSocket("udp4")
    socket.send(Buffer.from(JSON.stringify(packet)), UDP_PORT, "127.0.0.1", (error) => {
      socket.close()
      if (error) reject(error)
      else resolve()
    })
  })
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

  // Opening something from the dashboards' side brings the data back.
  await page.getByTestId("space-dashboards").click()
  await page.getByTestId("command-queries").click()
  await expect(page.getByTestId("dashboards-space")).toHaveCount(0)

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

  const cpu = (ts: number, uptime: number) => ({
    action: "monitor-cpu", appkey: key, host, time: String(ts),
    data: { cpu: [10, 5, 15], uptime, loadavg: [0.1, 0.2, 0.3] },
  })
  const now = Math.floor(Date.now() / 1000)
  for (const offset of [90, 60, 30]) await send(cpu(now - offset, 5000 - offset))
  await send({
    action: "monitor-ps", appkey: key, host, time: String(now),
    data: [
      { PCPU: "%CPU", PMEM: "%MEM", PID: "PID", PPID: "PPID", USER: "USER", ELAPSED: "ELAPSED", COMMAND: "COMMAND" },
      { PCPU: "7.5", PMEM: "1.0", PID: "4242", PPID: "1", USER: "root", ELAPSED: "00:10", COMMAND: "e2e-worker" },
    ],
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
    await expect(page.getByTestId("add-widgets-tree").getByText(host, { exact: true })).toBeVisible({ timeout: 2000 })
  }).toPass({ timeout: 30_000 })

  await page.getByTestId("add-widgets-tree").getByText(host, { exact: true }).click()
  await expect(page.getByTestId("add-widgets-presets")).toContainText("Linux host for")
  // A host that reports cpu and its processes fills four of the nine recipes.
  await expect(page.getByTestId("add-widgets-presets")).toContainText("4 of 9 widgets")
  await page.getByTestId("add-preset-linux-host").click()

  await expect(page.getByTestId("widget")).toHaveCount(4)
  await expect(page.getByTestId("processes-widget")).toContainText("e2e-worker")
  const uptime = page.getByTestId("stat-value")
  await expect(uptime).toHaveText("1 h 22 min")

  await send(cpu(Math.floor(Date.now() / 1000), 5000 + 180))
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

test("an agent's packets become a dashboard of widgets", async ({ page }) => {
  await login(page)
  test.skip(!(await storeIsReady(page)), "The metrics store is not set up on this stack")
  const agentName = `e2e-agent-${Date.now()}`
  const host = `e2e-host-${Date.now()}`

  await page.getByTestId("agents-open").click()
  await page.getByTestId("agent-name").fill(agentName)
  await page.getByTestId("agent-register").click()
  const key = (await page.getByTestId("agent-key").innerText()).trim()
  expect(key.length).toBeGreaterThanOrEqual(32)
  await expect(page.getByTestId("agent-snippet")).toContainText(`API_KEY: ${key}`)
  await expect(page.getByTestId("agent-snippet")).not.toContainText("iftop")
  await page.getByTestId("agents-dialog").getByRole("button", { name: "Close", exact: true }).click()

  // The metrics process reads keys again on an unknown one at most once a
  // second; a packet later than that is accepted whenever the keys were read.
  await page.waitForTimeout(1500)
  const now = Math.floor(Date.now() / 1000)
  for (const offset of [120, 90, 60, 30, 0]) {
    await send({
      action: "monitor-cpu",
      appkey: key,
      host,
      time: String(now - offset),
      data: { cpu: [10 + offset / 10, 5, 15], uptime: 5000 - offset, loadavg: [0.1, 0.2, 0.3] },
    })
  }

  const dashboardName = `e2e-dashboard-${Date.now()}`
  await page.getByTestId("dashboard-new").click()
  await expect(page.getByTestId("dashboard-view")).toBeVisible()
  await page.getByRole("button", { name: "Rename this dashboard" }).click()
  await page.getByTestId("dashboard-rename-input").fill(dashboardName)
  await page.getByTestId("dashboard-rename-input").press("Enter")
  await expect(page.getByTestId("dashboard-name")).toHaveText(dashboardName)
  await expect(page.getByTestId(`dashboard-${dashboardName}`)).toBeVisible()

  // Written in batches of a second; the catalog is read again when asked.
  await expect(async () => {
    await page.reload()
    await page.getByTestId("dashboard-add").click()
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

test("a host whose agent keeps restarting needs its owner, and the sheet names the iftop crash", async ({ page }) => {
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

  // What the crashing agent sent on 2026-09-13: every table says it has run
  // 32 seconds, 34 seconds after the one before.
  const now = Math.floor(Date.now() / 1000)
  for (const ago of [102, 68, 34, 0]) {
    await send({
      action: "monitor-ps", appkey: key, host, time: String(now - ago),
      data: [
        { PCPU: "%CPU", PMEM: "%MEM", PID: "PID", PPID: "PPID", USER: "USER", ELAPSED: "ELAPSED", COMMAND: "COMMAND" },
        {
          PCPU: "0.0", PMEM: "0.0", PID: "1", PPID: "0", USER: "root", ELAPSED: "00:32",
          COMMAND: "./sys_monitor_agent 192.168.65.254 9999 30 --actions=ps:30,cpu:30,iftop:30 --apikey=",
        },
      ],
    })
  }

  const item = page.getByTestId("attention-section").getByText(`${host} keeps restarting`)
  await expect(async () => {
    await page.reload()
    await page.getByTestId("activity-indicator").click()
    await expect(item).toBeVisible({ timeout: 2000 })
  }).toPass({ timeout: 30_000 })
  const row = page.locator("[data-testid^='attention-restarts:']").filter({ hasText: host })
  await expect(row).toContainText(`The agent ${agentName} restarted 3 times in the last 15 minutes`)
  await expect(row).toContainText("take it out of ACTIONS")

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
