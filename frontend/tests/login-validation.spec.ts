import { expect, test } from "@playwright/test"

test("missing credentials name the fields without attempting sign-in", async ({ page }) => {
  const attempts: string[] = []
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/login/access-token")) {
      attempts.push(request.url())
    }
  })
  await page.goto("/login")
  const email = page.getByTestId("login-email")
  const password = page.getByTestId("login-password")
  const submit = page.getByTestId("login-submit")
  await email.fill("")
  await password.fill("")
  await expect(submit).toBeEnabled()
  await submit.click()
  await expect(page.getByText("Email is required", { exact: true })).toBeVisible()
  await expect(page.getByText("Password is required", { exact: true })).toBeVisible()
  await expect(email).toHaveAttribute("aria-invalid", "true")
  await expect(password).toHaveAttribute("aria-invalid", "true")
  await expect(page.getByTestId("login-error")).toHaveCount(0)

  await email.fill("person@example.com")
  await password.press("Enter")
  await expect(page.getByText("Email is required", { exact: true })).toHaveCount(0)
  await expect(page.getByText("Password is required", { exact: true })).toBeVisible()
  expect(attempts).toEqual([])
})
