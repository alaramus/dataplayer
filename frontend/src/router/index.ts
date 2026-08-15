import { createRouter, createWebHistory } from "vue-router"

import { useAuthStore } from "@/stores/auth"

export const router = createRouter({
  history: createWebHistory(),
  routes: [
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
