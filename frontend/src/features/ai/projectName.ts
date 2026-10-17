import { t } from "@/shared/i18n"

/**
 * The name a new project is offered: "New project", numbered once that is
 * taken, because two alike in the list of chats could not be told apart.
 */
export function freshProjectName(taken: readonly string[]): string {
  const names = new Set(taken)
  const fresh = t("ai.project_name.fresh")
  if (!names.has(fresh)) return fresh
  let number = 2
  while (names.has(t("ai.project_name.numbered", { n: number }))) number += 1
  return t("ai.project_name.numbered", { n: number })
}
