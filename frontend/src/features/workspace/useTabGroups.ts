import { ref, shallowRef } from "vue"

import type { ConfirmRequest, Toast } from "@/shared/ui"
import type { WorkspaceApi } from "@/shared/workspace"

import { groupNameProblem, groupsKey, groupWarningKey, parseGroups, serializeGroups, validGroupSnapshot } from "./groups"
import type { TabGroup } from "./groups"
import type { Panel } from "./panels"

export function useTabGroups(
  userId: string,
  workspace: Pick<WorkspaceApi<Panel>, "snapshot" | "restore">,
  confirm: (request: ConfirmRequest) => Promise<boolean>,
  toast: Toast,
  storage: Storage = localStorage
) {
  const groups = shallowRef<TabGroup[]>([])
  const busy = ref(false)
  try {
    const saved = parseGroups(storage.getItem(groupsKey(userId)))
    if (saved === null) toast.error("The saved tab groups could not be read.")
    else groups.value = saved
  } catch {
    toast.error("The browser could not read the saved tab groups.")
  }

  function write(next: TabGroup[]): boolean {
    try {
      storage.setItem(groupsKey(userId), serializeGroups(next))
      groups.value = next
      return true
    } catch {
      toast.error("The browser could not save the tab groups. Your saved groups have not changed.")
      return false
    }
  }

  function save(name: string): boolean {
    if (busy.value || groupNameProblem(name, groups.value)) return false
    const snapshot = workspace.snapshot()
    if (!validGroupSnapshot(snapshot)) {
      toast.error("This layout could not be saved as a tab group.")
      return false
    }
    return write([...groups.value, { id: crypto.randomUUID(), name: name.trim(), snapshot }])
  }

  function rename(id: string, name: string): boolean {
    if (busy.value || groupNameProblem(name, groups.value, id)) return false
    return write(groups.value.map((group) => group.id === id ? { ...group, name: name.trim() } : group))
  }

  function update(id: string): boolean {
    if (busy.value) return false
    const snapshot = workspace.snapshot()
    if (!validGroupSnapshot(snapshot)) {
      toast.error("This layout could not be saved as a tab group.")
      return false
    }
    return write(groups.value.map((group) => group.id === id ? { ...group, snapshot } : group))
  }

  async function remove(group: TabGroup) {
    if (busy.value) return
    busy.value = true
    try {
      if (await confirm({
        title: "Delete tab group?", message: `Delete "${group.name}"? Your currently open tabs will stay open.`,
        confirmLabel: "Delete", danger: true,
      })) write(groups.value.filter((one) => one.id !== group.id))
    } finally {
      busy.value = false
    }
  }

  async function open(group: TabGroup) {
    if (busy.value) return
    busy.value = true
    try {
      let skipWarning = false
      try { skipWarning = storage.getItem(groupWarningKey(userId)) === "true" } catch { /* Ask when unavailable. */ }
      if (!skipWarning && !(await confirm({
        title: "Replace current tabs?",
        message: `Opening "${group.name}" replaces the current tabs and column layout with this saved group. Tabs outside the group will disappear.`,
        confirmLabel: "Open group",
        rememberLabel: "Don't show again",
        onRemember: () => {
          try { storage.setItem(groupWarningKey(userId), "true") }
          catch { toast.error("The browser could not remember this preference.") }
        },
      }))) return
      const outcome = await workspace.restore(group.snapshot)
      if (outcome === "invalid") toast.error("This saved tab group cannot be restored.")
      if (outcome === "changed") toast.info("The open tabs changed while confirming. Open the group again when ready.")
    } catch {
      toast.error("The tab group could not be opened.")
    } finally {
      busy.value = false
    }
  }

  return { groups, busy, save, rename, update, remove, open }
}

export type TabGroupLibrary = ReturnType<typeof useTabGroups>
