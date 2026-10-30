import { createRouter, createWebHistory } from "vue-router"

import { useAuthStore } from "@/stores/auth"
import { serverContext } from "@/shared/servers/context"
import { mayLeaveServer } from "@/shared/servers/leaving"
import { routeServerTarget } from "@/shared/servers/profiles"
import type { RouteRecordRaw } from "vue-router"

// The kit showcase is a development tool and is not part of the application a
// user gets. Behind import.meta.env.DEV the bundler drops both the route and
// the page from a production build.
const devRoutes: RouteRecordRaw[] = import.meta.env.DEV
  ? [
      {
        path: "/ui-kit",
        name: "ui-kit",
        // No auth: the showcase renders no server data, so it opens without a
        // running backend.
        component: () => import("@/features/dev/UiKitPage.vue"),
      },
      {
        path: "/workspace-demo",
        name: "workspace-demo",
        // The engine renders no server data, so it opens without a backend.
        component: () => import("@/features/dev/WorkspaceDemoPage.vue"),
      },
    ]
  : []

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...devRoutes,
    {
      path: "/connect-server",
      name: "connect-server",
      component: () => import("@/features/servers/ServerConnectPage.vue"),
    },
    {
      path: "/login",
      name: "login",
      component: () => import("@/features/auth/LoginPage.vue"),
    },
    {
      // A link a superuser handed on: the person chooses their password here,
      // before they can sign in at all.
      path: "/set-password",
      name: "set-password",
      component: () => import("@/features/auth/SetPasswordPage.vue"),
    },
    {
      // A shared link. It resolves here and then hands the workspace what to
      // open, so the address stays out of the workspace's own URL (D60).
      path: "/s/:token",
      name: "shared",
      component: () => import("@/features/shares/ShareLandingPage.vue"),
      meta: { requiresAuth: true },
    },
    {
      // A link to a dashboard: its address, carrying no right (D129).
      path: "/dashboards/:dashboardId",
      name: "dashboard-link",
      component: () => import("@/features/dashboards/DashboardLinkPage.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/",
      name: "workspace",
      component: () => import("@/features/workspace/WorkspacePage.vue"),
      meta: { requiresAuth: true },
    },
    {
      // What this account chose for itself, which every signed-in user has.
      // Its own address rather than a dialog off the menu: a preference is
      // something to come back to and to link somebody to.
      //
      // The section is part of the address so that a link into one of them is
      // a link; an address that names none opens the first.
      path: "/preferences/:section?",
      name: "preferences",
      component: () => import("@/features/preferences/PreferencesPage.vue"),
      meta: { requiresAuth: true },
    },
    {
      // Whether the signed-in user is an administrator is not known here: it
      // is server state, and a guard that waited for it would hold every
      // navigation. The page says so instead, and the routes behind it answer
      // 403 regardless — see D34.
      //
      // The section is part of the address so that a link into one of them is
      // a link; an address that names none opens the first.
      path: "/admin/:section?",
      name: "admin",
      component: () => import("@/features/admin/AdminPage.vue"),
      meta: { requiresAuth: true },
    },
    {
      // Where accounts used to live, kept so that a bookmark still works.
      path: "/users",
      redirect: { name: "admin", params: { section: "users" } },
    },
  ],
})

router.beforeEach(async (to, from) => {
  if (to.name === "connect-server") return true
  const context = serverContext()
  const target = routeServerTarget(to.query.server, to.name === "shared", context.active.url, context.defaultServer.url)
  if (target !== null) {
    // A link opened inside the app must not unmount its unsaved workspace
    // before the connection page gets a chance to ask about switching.
    if (from.meta.requiresAuth && !(await mayLeaveServer())) return false
    return { name: "connect-server", query: { server: target, next: to.fullPath } }
  }
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    // Where they were going is kept: somebody who opened a shared link while
    // signed out is meant to arrive at it, not at an empty workspace.
    return to.name === "workspace"
      ? { name: "login" }
      : { name: "login", query: { next: to.fullPath } }
  }
  if (to.name === "login" && auth.isLoggedIn) {
    return { name: "workspace" }
  }
  return true
})
