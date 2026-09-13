import { ref } from "vue"

/**
 * A dashboard somebody followed a link to, waiting for the dashboards to open
 * it. A module ref, like the shared view's: one screen handing another an id
 * it already has, and nothing the server needs to know.
 */
const pending = ref<string | null>(null)

export function setDashboardIntent(dashboardId: string): void {
  pending.value = dashboardId
}

export function takeDashboardIntent(): string | null {
  const dashboardId = pending.value
  pending.value = null
  return dashboardId
}
