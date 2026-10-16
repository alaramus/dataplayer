<script setup lang="ts">
import { provide, watch } from "vue"

import { t } from "@/shared/i18n"
import { createOperations, isActive, operationsKey } from "@/shared/operations"
import ServerBoundary from "@/features/servers/ServerBoundary.vue"
import QuickChatWindow from "@/features/ai/QuickChatWindow.vue"
import AccountLanguage from "@/features/preferences/AccountLanguage.vue"
import { useServerLeaveGuard } from "@/shared/servers/leaving"
import { confirmInWindow, provideWindows, useWindows, WindowHost } from "@/shared/windows"
import { useAuthStore } from "@/stores/auth"

const operations = createOperations()
provide(operationsKey, operations)
const auth = useAuthStore()
watch(() => auth.token, () => operations.clear(), { flush: "sync" })

// One host for every route: anything transient opens in the same window
// system, regardless of which feature asked for it.
const windows = useWindows()
provideWindows(windows)
useServerLeaveGuard(async () => {
  for (const entry of [...windows.context.windows.value]) {
    const guard = entry.beforeClose ?? (() => windows.context.confirmClose?.(entry.id) ?? true)
    if (!(await guard())) return false
  }
  if (operations.items.value.some(isActive)) {
    return await confirmInWindow(windows, {
      title: t("shell.leave_work.title"),
      message: t("shell.leave_work.message"),
      confirmLabel: t("shell.leave_work.confirm"),
      danger: true,
    })
  }
  return true
})
</script>

<template>
  <ServerBoundary>
    <router-view />
  </ServerBoundary>
  <QuickChatWindow v-if="auth.token" />
  <AccountLanguage v-if="auth.token" />
  <WindowHost :context="windows.context" />
</template>
