import { expect } from "@playwright/test"
import type { Page } from "@playwright/test"

import { REDIS } from "./redis"
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

/** Choose a tab color in the connector form that is already open. */
export async function chooseTabColor(page: Page, color: string) {
  await page.getByTestId("connector-tab-color").click()
  const picker = page.getByRole("dialog", { name: "Tab color", exact: true })
  await picker.getByRole("textbox").fill(color)
  await page.keyboard.press("Escape")
  await expect(picker).toBeHidden()
}

/**
 * The window's page for who may reach a connection and what may be done
 * through it, rather than how to reach it (D66).
 *
 * A step of its own because scenarios go there for different things — the
 * policy, sharing, what a colleague was given — and because the name and the
 * fields are on the page it leaves.
 */
export async function openPermissions(page: Page) {
  await page.getByTestId("connector-tab-permissions").click()
}

/**
 * The window's page for how this connection behaves rather than how to reach
 * it: nobody's first question, so it has a page of its own (D105).
 */
export async function openOptions(page: Page) {
  await page.getByTestId("connector-tab-options").click()
}

/** Set how far a console may go, in the window that is already open. */
export async function choosePolicy(page: Page, label: string) {
  await openPermissions(page)
  await page.getByTestId("connector-policy").click()
  await page.getByRole("option", { name: label, exact: true }).click()
}

/** Personal storage has no options: the server composes the root itself. */
export async function createFileConnector(page: Page, name: string) {
  await pickAdapterType(page, "file")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()
}

/** The development Redis, opening on the scenarios' own database. */
export async function createRedisConnector(page: Page, name: string) {
  await pickAdapterType(page, "redis")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("field-auth_method").click()
  await page.getByRole("option", { name: "No auth", exact: true }).click()
  await page.getByTestId("field-host").fill(REDIS.serverHost)
  await page.getByTestId("field-database").fill(String(REDIS.database))
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()
}

/**
 * The SSH server as the backend container sees it: `sshd` from
 * compose.override.yml. The connection signs in with the password — a key
 * made in a scenario would first have to reach the server's authorized_keys,
 * which a browser cannot do.
 */
export const SSH_SERVER = { host: "sshd", port: "2222", user: "dataplayer", password: "dataplayer" }

/** The connection form of an SSH server, filled in and signing in with the password. */
export async function fillSshServer(page: Page, name: string) {
  await pickAdapterType(page, "ssh")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("field-host").fill(SSH_SERVER.host)
  await page.getByTestId("field-port").fill(SSH_SERVER.port)
  await page.getByTestId("field-username").fill(SSH_SERVER.user)
  await page.getByTestId("field-auth_method").click()
  await page.getByRole("option", { name: "Password", exact: true }).click()
  await page.getByTestId("field-password").fill(SSH_SERVER.password)
}

/** An SSH connection whose server key was fetched and trusted, saved (D145). */
export async function createSshConnector(page: Page, name: string) {
  await fillSshServer(page, name)
  await page.getByTestId("server-key-fetch").click()
  await page.getByTestId("server-key-trust").click()
  await expect(page.getByTestId("server-key-pinned")).toContainText("SHA256:")
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()
}
