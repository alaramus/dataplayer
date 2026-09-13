<script setup lang="ts">
import { onMounted } from "vue"
import { useRoute, useRouter } from "vue-router"

import { AppSpinner } from "@/shared/ui"
import { useSpaceStore } from "@/stores/space"

import { setDashboardIntent } from "./intent"

/**
 * Where a link to a dashboard lands: it hands the id to the dashboards and
 * steps aside, so the address stays out of the workspace's own URL. Whether
 * the reader may see it is answered when it is opened (D129).
 */
const route = useRoute()
const router = useRouter()
const space = useSpaceStore()

onMounted(() => {
  const dashboardId = route.params.dashboardId
  if (typeof dashboardId === "string") setDashboardIntent(dashboardId)
  space.show("dashboards")
  void router.replace({ name: "workspace" })
})
</script>

<template>
  <div class="dashboard-link">
    <AppSpinner />
  </div>
</template>

<style scoped>
.dashboard-link {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
}
</style>
