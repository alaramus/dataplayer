/**
 * Whether a line stands before this chat in its group of the history: it is
 * the first one not pinned, after chats that are. Pinned chats come first in
 * every group, so there is at most one line in each.
 */
export function pinnedRuleBefore(chats: readonly { chat: { pinned?: boolean } }[], index: number): boolean {
  const previous = chats[index - 1]
  const current = chats[index]
  return previous?.chat.pinned === true && current !== undefined && current.chat.pinned !== true
}
