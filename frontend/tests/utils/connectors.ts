import { expect } from "@playwright/test"
import type { Page } from "@playwright/test"

import { connectorRow } from "./workspace"

/**
 * Registering a connection, the way a user does it.
 *
 * Four scenarios needed the same twelve lines, and they had begun to drift:
 * the address of the database was written out in each of them. It is written
 * once here, and as the backend container sees it — the check and every query
 * run on the server, so `localhost` would name the wrong machine.
 */
export const DATABASE = {
  host: process.env.POSTGRES_SERVER ?? "db",
  port: process.env.POSTGRES_PORT ?? "5432",
  database: process.env.POSTGRES_DB ?? "app",
  user: process.env.POSTGRES_USER ?? "postgres",
  password: process.env.POSTGRES_PASSWORD ?? "",
}

/**
 * The first of the two windows: which kind of source.
 *
 * Written once here because every scenario below starts with it, and because
 * it is the step that replaced a dropdown — a helper is what keeps the change
 * from being made twelve times.
 */
export async function pickAdapterType(page: Page, adapterType: string) {
  await page.getByTestId("add-connector").click()
  await page.getByTestId(`adapter-${adapterType}`).click()
  await page.getByTestId("create-from-catalog").click()
  await expect(page.getByTestId("connector-name")).toBeVisible()
}

export async function createPostgresConnector(page: Page, name: string) {
  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("field-port").fill(DATABASE.port)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await page.getByTestId("field-password").fill(DATABASE.password)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()
}

/** Personal storage has no options: the server composes the root itself. */
export async function createFileConnector(page: Page, name: string) {
  await pickAdapterType(page, "file")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()
}
