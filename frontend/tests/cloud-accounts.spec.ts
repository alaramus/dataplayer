import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

/**
 * A person's cloud accounts on the Preferences page (D451, D452).
 *
 * No provider is installed yet, so nothing here reaches a cloud: the account
 * is kept, refused where it is wrong, changed without retyping its secret and
 * deleted. Values are AWS's documented examples, not credentials.
 */

const SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

test("an account is kept, refused in words, changed and deleted, its secret never shown", async ({
  page,
}) => {
  const name = `e2e-cloud-${Date.now()}`
  await login(page)
  await page.goto("/preferences/cloud-accounts")

  await page.getByTestId("cloud-account-new").click()
  const dialog = page.getByTestId("cloud-account-dialog")
  await dialog.getByTestId("cloud-account-name").fill(name)
  await dialog.getByTestId("field-access_key_id").fill("AKIAIOSFODNN7EXAMPLE")
  await dialog.getByTestId("field-secret_access_key").fill(SECRET)
  await dialog.getByTestId("field-role_arn").fill("reader")
  await dialog.getByTestId("cloud-account-save").click()
  // Said on the field, as a sentence rather than a pattern.
  await expect(dialog).toContainText("A role is named by its ARN")

  await dialog.getByTestId("field-role_arn").fill("")
  await dialog.getByTestId("cloud-account-save").click()
  const row = page.getByTestId(`cloud-account-${name}`)
  await expect(row).toContainText("Amazon Web Services · Access key")
  await expect(row).toContainText("No connection uses it")
  // Nothing installed can test it yet, so nothing offers to.
  await expect(page.getByTestId(`cloud-account-test-${name}`)).toHaveCount(0)
  await expect(page.getByTestId("cloud-accounts")).not.toContainText(SECRET)

  // Changed without retyping the secret: it stays stored on the server.
  const saved = page.waitForResponse((response) => response.request().method() === "PATCH")
  await page.getByTestId(`cloud-account-edit-${name}`).click()
  await expect(dialog.getByTestId("cloud-account-kind")).toBeDisabled()
  await expect(dialog.getByTestId("field-secret_access_key")).not.toHaveValue(SECRET)
  await dialog.getByTestId("field-region").fill("eu-west-1")
  await dialog.getByTestId("cloud-account-save").click()
  const answer = await saved
  expect(answer.status()).toBe(200)
  const body = (await answer.json()) as { settings: { region: string }; stored_secrets: string[] }
  expect(body.settings.region).toBe("eu-west-1")
  expect(body.stored_secrets).toContain("secret_access_key")
  expect(JSON.stringify(body)).not.toContain(SECRET)

  await page.getByTestId(`cloud-account-delete-${name}`).click()
  await page.getByTestId("confirm-accept").click()
  await expect(row).toHaveCount(0)
})

test("the server's own identity is not offered while the installation does not lend it", async ({
  page,
}) => {
  await login(page)
  const schema = page.waitForResponse((response) => response.url().endsWith("/cloud-accounts/schema"))
  await page.goto("/preferences/cloud-accounts")
  await page.getByTestId("cloud-account-new").click()

  const answer = (await (await schema).json()) as { ambient: boolean }
  test.skip(answer.ambient, "This installation lends its own identity (CLOUD_AMBIENT_CREDENTIALS)")
  // One way left for AWS, so there is nothing to choose between.
  await expect(page.getByTestId("cloud-account-dialog")).not.toContainText("This server's credentials")
  await expect(page.getByTestId("field-method")).toHaveCount(0)
})
