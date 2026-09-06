/**
 * Whether to warn before reading every file below a folder.
 *
 * Searching inside files is minutes where searching names is milliseconds, so
 * the first one asks — once, because a dialog in front of every search is one
 * people learn to click through. The answer is this browser's: it is about a
 * habit rather than about the data.
 */

export const ASK_KEY = "dataplayer-content-search-ask"

/**
 * Whether the warning should be shown.
 *
 * Anything but the exact remembered "no" means yes, including a storage that
 * cannot be read: a private window forgetting the answer costs one dialog,
 * while a failure that silently meant "do not ask" would start a minutes-long
 * search on a keypress nobody was warned about.
 */
export function shouldAsk(storage: Pick<Storage, "getItem">): boolean {
  try {
    return storage.getItem(ASK_KEY) !== "never"
  } catch {
    return true
  }
}

/** Remember that this browser has been told, or forget that it was. */
export function rememberAnswer(
  storage: Pick<Storage, "setItem" | "removeItem">,
  ask: boolean
): void {
  try {
    if (ask) storage.removeItem(ASK_KEY)
    else storage.setItem(ASK_KEY, "never")
  } catch {
    // A browser that will not store it asks again next time, which is the
    // safe half of the choice.
  }
}
