import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

const DATABASE = {
  host: process.env.POSTGRES_SERVER ?? "localhost",
  port: process.env.POSTGRES_PORT ?? "5432",
  database: process.env.POSTGRES_DB ?? "app",
  user: process.env.POSTGRES_USER ?? "postgres",
  password: process.env.POSTGRES_PASSWORD ?? "",
}

// Quasar пробрасывает data-testid на сам элемент ввода, поэтому идентификаторы
// полей адресуют input напрямую, без вложенного локатора.
async function fillConnectionFields(
  page: import("@playwright/test").Page,
  password: string
) {
  await page.getByTestId("connector-type").click()
  await page.getByRole("option", { name: "PostgreSQL" }).click()

  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("field-port").fill(DATABASE.port)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await page.getByTestId("field-password").fill(password)
}

test("создание подключения, проверка соединения и удаление", async ({ page }) => {
  const name = `e2e-postgres-${Date.now()}`
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("connector-name").fill(name)
  await fillConnectionFields(page, DATABASE.password)

  await page.getByTestId("check-draft").click()
  const result = page.getByTestId("check-result")
  await expect(result).toBeVisible()
  await expect(result).toHaveClass(/bg-positive/)

  await page.getByTestId("save-connector").click()
  await expect(page.getByTestId("connector-table")).toContainText(name)

  await page.getByTestId(`check-${name}`).click()
  await expect(page.locator(".q-notification").first()).toBeVisible()

  await page.getByTestId(`delete-${name}`).click()
  await page.getByRole("button", { name: "Удалить" }).click()
  await expect(page.getByTestId("connector-table")).not.toContainText(name)
})

test("неверный пароль показывает ошибку аутентификации без утечки пароля", async ({
  page,
}) => {
  const wrongPassword = "definitely-not-the-password"
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("connector-name").fill(`e2e-bad-${Date.now()}`)
  await fillConnectionFields(page, wrongPassword)

  await page.getByTestId("check-draft").click()

  const result = page.getByTestId("check-result")
  await expect(result).toBeVisible()
  await expect(result).toHaveClass(/bg-negative/)
  await expect(result).toContainText("Ошибка аутентификации")
  await expect(result).not.toContainText(wrongPassword)
})

test("секретное поле при редактировании пустое и не требует повторного ввода", async ({
  page,
}) => {
  const name = `e2e-edit-${Date.now()}`
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("connector-name").fill(name)
  await fillConnectionFields(page, DATABASE.password)
  await page.getByTestId("save-connector").click()
  await expect(page.getByTestId("connector-table")).toContainText(name)

  await page.getByTestId(`edit-${name}`).click()
  await expect(page.getByTestId("field-password")).toHaveValue("")

  // Пароль не вводим: сервер подставит сохранённый по connector_id.
  await page.getByTestId("check-draft").click()
  await expect(page.getByTestId("check-result")).toHaveClass(/bg-positive/)

  await page.getByRole("button", { name: "Отмена" }).click()
  await page.getByTestId(`delete-${name}`).click()
  await page.getByRole("button", { name: "Удалить" }).click()
  await expect(page.getByTestId("connector-table")).not.toContainText(name)
})
