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
      path: "/",
      name: "connectors",
      component: () => import("@/features/connectors/ConnectorsPage.vue"),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return { name: "login" }
  }
  if (to.name === "login" && auth.isLoggedIn) {
    return { name: "connectors" }
  }
  return true
})
