import { ref } from "vue"

/**
 * Which connection's Search index window is open (D212).
 *
 * Opened from four places — the catalog's Actions menu, the tool at the foot,
 * the connection window and a cell of the Search tab — and drawn once by the
 * workspace, so none of them mounts a window of its own.
 */
export interface IndexedConnection {
  id: string
  name: string
}

const asked = ref<IndexedConnection | null>(null)

export function useSearchIndexWindow() {
  return {
    asked,
    open(connection: IndexedConnection) {
      asked.value = { ...connection }
    },
    close() {
      asked.value = null
    },
  }
}
