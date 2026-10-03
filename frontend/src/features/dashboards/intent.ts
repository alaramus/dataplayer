import { readonly, ref } from "vue"

/**
 * A dashboard asked for from elsewhere — a link followed, a search hit —
 * waiting for the dashboards to open it. A module ref, like the shared view's:
 * one screen handing another an id it already has, and nothing the server
 * needs to know.
 *
 * Watched rather than read once: the space is kept alive once it has been
 * shown (D125), and its setup does not run again for a later request.
 */
const pending = ref<string | null>(null)

export const dashboardIntent = readonly(pending)

export function setDashboardIntent(dashboardId: string): void {
  pending.value = dashboardId
}

export function takeDashboardIntent(): string | null {
  const dashboardId = pending.value
  pending.value = null
  return dashboardId
}
