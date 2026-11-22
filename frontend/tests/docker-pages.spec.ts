import { execFile } from "node:child_process"
import { promisify } from "node:util"
import { fileURLToPath } from "node:url"

import { expect, test } from "@playwright/test"

import { pickAdapterType } from "./utils/connectors"
import { login } from "./utils/login"
import { requireE2EService } from "./utils/services"
import { catalogRow, openNode } from "./utils/catalog"
import { deleteConnector, openConnector } from "./utils/workspace"

const execFileAsync = promisify(execFile)
const REPOSITORY_ROOT = fileURLToPath(new URL("../../", import.meta.url))
const DOCKER_TIMEOUT_MS = 300_000

async function dockerRemote(...args: string[]) {
  await execFileAsync(
    "docker",
    ["compose", "exec", "-T", "docker-remote", "docker", ...args],
    { cwd: REPOSITORY_ROOT, encoding: "utf8", timeout: DOCKER_TIMEOUT_MS, windowsHide: true }
  )
}

async function makeContainer(name: string, project: string) {
  await dockerRemote("pull", "alpine:3.20")
  await dockerRemote("run", "-d", "--name", name,
    "--label", `com.docker.compose.project=${project}`,
    "--label", "com.docker.compose.service=web",
    "alpine:3.20", "sh", "-c", "echo ready; sleep 100000")
}

async function createDockerSsh(page: import("@playwright/test").Page, name: string) {
  await pickAdapterType(page, "ssh")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("field-host").fill("docker-remote")
  await page.getByTestId("field-port").fill("22")
  await page.getByTestId("field-username").fill("dataplayer")
  await page.getByTestId("field-auth_method").click()
  await page.getByRole("option", { name: "Password", exact: true }).click()
  await page.getByTestId("field-password").fill("dataplayer")
  await page.getByTestId("server-key-fetch").click()
  await page.getByTestId("server-key-trust").click()
  await page.getByTestId("save-connector").click()
  await expect(page.getByTestId(`connector-${name}`)).toBeVisible()
}

async function createDockerConnector(
  page: import("@playwright/test").Page,
  name: string,
  sshName: string
) {
  await pickAdapterType(page, "docker")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("field-ssh_connection").click()
  await page.getByRole("option", { name: sshName, exact: true }).click()
  await page.getByTestId("save-connector").click()
  await expect(page.getByTestId(`connector-${name}`)).toBeVisible()
}

async function openJsonAndReturn(page: import("@playwright/test").Page, title: string) {
  await expect(page.getByTestId("view-body")).toBeVisible()
  await expect(page.getByTestId("view-show-tree")).toHaveAccessibleName("As JSON")
  await page.getByTestId("view-show-tree").click()
  const jsonTab = page.getByRole("tab", { name: `${title} — As JSON`, exact: true })
  await expect(jsonTab).toHaveAttribute("aria-selected", "true")
  await expect(page.getByTestId("tree-body")).toBeVisible()
  await page.getByRole("tab", { name: title, exact: true }).click()
  await expect(page.getByTestId("view-body")).toBeVisible()
}

test("Docker nodes open as cards with separate pages", async ({ page }) => {
  await requireE2EService("docker-remote")
  const suffix = Date.now()
  const sshName = `e2e-d423-ssh-${suffix}`
  const dockerName = `e2e-d423-docker-${suffix}`
  const containerName = `e2e-d423-web-${suffix}`
  const projectName = `e2e-d423-${suffix}`
  let sshCreated = false
  let dockerCreated = false
  let containerCreated = false

  await login(page)
  try {
    await makeContainer(containerName, projectName)
    containerCreated = true
    await createDockerSsh(page, sshName)
    sshCreated = true
    await createDockerConnector(page, dockerName, sshName)
    dockerCreated = true
    await openConnector(page, dockerName)

    await openNode(page, "Containers")
    await openNode(page, projectName)
    await catalogRow(page, containerName).click()
    await expect(page.getByTestId("view-title")).toContainText(containerName)
    await page.getByTestId("view-link").filter({ hasText: "alpine:3.20" }).click()
    await expect(page.getByTestId("view-title")).toContainText("alpine:3.20")
    await expect(page.getByTestId("view-page-0")).toHaveAccessibleName("History")
    await page.getByRole("tab", { name: containerName, exact: true }).click()
    await expect(page.getByTestId("view-body")).toBeVisible()

    // The container's actions sit over its view, by icon (D424).
    for (const [name, title] of [
      ["docker_stop", "Stop"],
      ["docker_terminal", "Terminal"],
      ["docker_remove_container", "Remove container"],
    ]) {
      await expect(page.getByTestId(`view-action-${name}`)).toHaveAccessibleName(title)
    }
    await expect(page.getByTestId("view-page-0")).toHaveAccessibleName("Logs")

    const logsTitle = `${containerName} — Logs`
    await page.getByTestId("view-page-0").click()
    const logsTab = page.getByRole("tab", { name: logsTitle, exact: true })
    await expect(logsTab).toBeVisible()
    await expect(logsTab).toHaveAttribute("aria-selected", "true")
    await expect(page.getByTestId("row-grid")).toBeVisible()
    await page.getByRole("tab", { name: containerName, exact: true }).click()
    await expect(page.getByTestId("view-body")).toBeVisible()
    await openJsonAndReturn(page, containerName)
    await page.getByTestId("catalog-up").click()
    await page.getByTestId("catalog-up").click()

    await openNode(page, "Images")
    await catalogRow(page, "alpine:3.20").click()
    await expect(page.getByTestId("view-title")).toContainText("alpine:3.20")

    const historyTitle = "alpine:3.20 — History"
    await page.getByTestId("view-page-0").click()
    const historyTab = page.getByRole("tab", { name: historyTitle, exact: true })
    await expect(historyTab).toBeVisible()
    await expect(historyTab).toHaveAttribute("aria-selected", "true")
    await expect(page.getByTestId("row-grid")).toBeVisible()
    await page.getByRole("tab", { name: "alpine:3.20", exact: true }).click()
    await expect(page.getByTestId("view-body")).toBeVisible()
    await openJsonAndReturn(page, "alpine:3.20")
  } finally {
    if (dockerCreated) await deleteConnector(page, dockerName)
    if (sshCreated) await deleteConnector(page, sshName)
    if (containerCreated) {
      await dockerRemote("rm", "-f", containerName).catch(() => undefined)
    }
  }
})
