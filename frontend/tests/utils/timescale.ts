import { execFile } from "node:child_process"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"

import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { pickAdapterType } from "./connectors"
import { connectorRow } from "./workspace"

const execFileAsync = promisify(execFile)
const REPOSITORY_ROOT = fileURLToPath(new URL("../../../", import.meta.url))
const COMPOSE = ["compose", "-f", "backend/compatibility/timescale/compose.yml"]
const SERVICE = "v2_30_pg17"

/**
 * The newest release of the compatibility matrix, as the backend container
 * reaches it. Its fixture role and password are the matrix's own, written in
 * its compose file; nothing here is a real credential.
 */
export const TIMESCALE = {
  host: "host.docker.internal",
  port: "55430",
  database: "timescale_fixture",
  user: "fixture_admin",
  password: "fixture-only",
}

/** Skip a scenario when the matrix source it needs is not running. */
export async function requireTimescale(): Promise<void> {
  try {
    const { stdout } = await execFileAsync(
      "docker",
      [...COMPOSE, "ps", "--services", "--filter", "status=running", SERVICE],
      { cwd: REPOSITORY_ROOT, encoding: "utf8", timeout: 5000, windowsHide: true }
    )
    if (stdout.split(/\r?\n/).some((line) => line.trim() === SERVICE)) return
  } catch {
    // Reported by the skip below.
  }
  test.skip(
    true,
    `The TimescaleDB 2.30 source is not running; start it with ` +
      `\`docker compose -f backend/compatibility/timescale/compose.yml up -d ${SERVICE}\``
  )
}

/**
 * Run fixture SQL on that source, as its own administrator.
 *
 * A scenario prepares the hypertable it changes, so it never edits one the
 * compatibility suite reads.
 */
export async function timescaleSql(sql: string): Promise<string> {
  const { stdout } = await execFileAsync(
    "docker",
    [
      ...COMPOSE, "exec", "-T", SERVICE, "psql", "-v", "ON_ERROR_STOP=1", "-At",
      "-U", TIMESCALE.user, "-d", TIMESCALE.database, "-c", sql,
    ],
    { cwd: REPOSITORY_ROOT, encoding: "utf8", timeout: 20000, windowsHide: true }
  )
  return stdout.trim()
}

export async function createTimescaleConnector(page: Page, name: string) {
  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("field-host").fill(TIMESCALE.host)
  await page.getByTestId("field-port").fill(TIMESCALE.port)
  await page.getByTestId("field-database").fill(TIMESCALE.database)
  await page.getByTestId("field-user").fill(TIMESCALE.user)
  await page.getByTestId("field-password").fill(TIMESCALE.password)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()
}
