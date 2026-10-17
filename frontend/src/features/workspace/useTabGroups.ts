import { computed, ref, shallowRef } from "vue"

import { t } from "@/shared/i18n"
import type { ConfirmRequest, Toast } from "@/shared/ui"
import type { WorkspaceApi } from "@/shared/workspace"

import { groupNameProblem, groupsKey, groupWarningKey, parseGroups, serializeGroups, validGroupSnapshot } from "./groups"
import type { TabGroup } from "./groups"
import type { Panel } from "./panels"

export function useTabGroups(
  userId: string,
  workspace: Pick<WorkspaceApi<Panel>, "panels" | "snapshot" | "restore">,
  confirm: (request: ConfirmRequest) => Promise<boolean>,
  toast: Toast,
  storage: Storage = localStorage
) {
  const groups = shallowRef<TabGroup[]>([])
  const busy = ref(false)
  const canSave = computed(() => workspace.panels.value.some((panel) => panel.kind !== "connectors"))
  try {
    const saved = parseGroups(storage.getItem(groupsKey(userId)))
    if (saved === null) toast.error(t("workspace.groups.read_failed"))
    else groups.value = saved
  } catch {
    toast.error(t("workspace.groups.browser_read_failed"))
  }

  function write(next: TabGroup[]): boolean {
    try {
      storage.setItem(groupsKey(userId), serializeGroups(next))
      groups.value = next
      return true
    } catch {
      toast.error(t("workspace.groups.browser_save_failed"))
      return false
    }
  }

  function save(name: string): boolean {
    if (busy.value || !canSave.value || groupNameProblem(name, groups.value)) return false
    const snapshot = workspace.snapshot()
    if (!validGroupSnapshot(snapshot)) {
      toast.error(t("workspace.groups.layout_not_saved"))
      return false
    }
    return write([...groups.value, { id: crypto.randomUUID(), name: name.trim(), snapshot }])
  }

  function rename(id: string, name: string): boolean {
    if (busy.value || groupNameProblem(name, groups.value, id)) return false
    return write(groups.value.map((group) => group.id === id ? { ...group, name: name.trim() } : group))
  }

  function update(id: string): boolean {
    if (busy.value || !canSave.value) return false
    const snapshot = workspace.snapshot()
    if (!validGroupSnapshot(snapshot)) {
      toast.error(t("workspace.groups.layout_not_saved"))
      return false
    }
    return write(groups.value.map((group) => group.id === id ? { ...group, snapshot } : group))
  }

  async function remove(group: TabGroup) {
    if (busy.value) return
    busy.value = true
    try {
      if (await confirm({
        title: t("workspace.groups.delete_title"),
        message: t("workspace.groups.delete_message", { name: group.name }),
        confirmLabel: t("workspace.groups.delete"), danger: true,
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
        title: t("workspace.groups.replace_title"),
        message: t("workspace.groups.replace_message", { name: group.name }),
        confirmLabel: t("workspace.groups.open_group"),
        rememberLabel: t("workspace.groups.dont_show_again"),
        onRemember: () => {
          try { storage.setItem(groupWarningKey(userId), "true") }
          catch { toast.error(t("workspace.groups.remember_failed")) }
        },
      }))) return
      const outcome = await workspace.restore(group.snapshot)
      if (outcome === "invalid") toast.error(t("workspace.groups.cannot_restore"))
      if (outcome === "changed") toast.info(t("workspace.groups.changed"))
    } catch {
      toast.error(t("workspace.groups.open_failed"))
    } finally {
      busy.value = false
    }
  }

  return { groups, busy, canSave, save, rename, update, remove, open }
}

export type TabGroupLibrary = ReturnType<typeof useTabGroups>
