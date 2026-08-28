<script setup lang="ts">
import { provideWindows, useWindows, WindowHost } from "@/shared/windows"

// One host for every route: anything transient opens in the same window
// system, regardless of which feature asked for it.
const windows = useWindows()
provideWindows(windows)
</script>

<template>
  <router-view />
  <WindowHost :context="windows.context" />
</template>
