/**
 * The name a new project is offered: "New project", numbered once that is
 * taken, because two alike in the list of chats could not be told apart.
 */
export function freshProjectName(taken: readonly string[]): string {
  const names = new Set(taken)
  if (!names.has("New project")) return "New project"
  let number = 2
  while (names.has(`New project ${String(number)}`)) number += 1
  return `New project ${String(number)}`
}
