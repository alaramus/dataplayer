<script setup lang="ts">
import { provide, watch } from "vue"

import { createOperations, operationsKey } from "@/shared/operations"
import { provideWindows, useWindows, WindowHost } from "@/shared/windows"
import { useAuthStore } from "@/stores/auth"

const operations = createOperations()
provide(operationsKey, operations)
const auth = useAuthStore()
watch(() => auth.token, () => operations.clear(), { flush: "sync" })

// One host for every route: anything transient opens in the same window
// system, regardless of which feature asked for it.
const windows = useWindows()
provideWindows(windows)
</script>

<template>
  <router-view />
  <WindowHost :context="windows.context" />
</template>
