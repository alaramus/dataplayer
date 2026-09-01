import { createRouter, createWebHistory } from "vue-router"

import { useAuthStore } from "@/stores/auth"
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
      path: "/login",
      name: "login",
      component: () => import("@/features/auth/LoginPage.vue"),
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
      path: "/",
      name: "workspace",
      component: () => import("@/features/workspace/WorkspacePage.vue"),
      meta: { requiresAuth: true },
    },
    {
      // Whether the signed-in user is an administrator is not known here: it
      // is server state, and a guard that waited for it would hold every
      // navigation. The page says so instead, and the routes behind it answer
      // 403 regardless — see D34.
      path: "/users",
      name: "users",
      component: () => import("@/features/admin/UsersPage.vue"),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach((to) => {
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
