import { defineStore } from "pinia"
import { ref } from "vue"

import { serverStorageKey } from "@/shared/servers/context"

/**
 * Which space fills the screen: the data workspace or the dashboards (D125).
 *
 * Pinia, because the server knows nothing about it (D6). Remembered per
 * browser and per server, like the layout it stands beside.
 */
export type Space = "data" | "dashboards"

const KEY = "dataplayer-space"

function stored(): Space {
  try {
    return localStorage.getItem(serverStorageKey(KEY)) === "dashboards" ? "dashboards" : "data"
  } catch {
    return "data"
  }
}

export const useSpaceStore = defineStore("space", () => {
  const current = ref<Space>(stored())

  function show(space: Space) {
    current.value = space
    try {
      localStorage.setItem(serverStorageKey(KEY), space)
    } catch {
      // A browser that refuses storage still switches; it just forgets.
    }
  }

  return { current, show }
})
