export function emptyRecipientsMessage(directoryCount: number, candidateCount: number): string {
  if (candidateCount > 0) return ""
  return directoryCount === 0
    ? "No other active accounts are available. Ask an administrator to create or enable an account, then reopen Share."
    : "All other active accounts already have access. Change their access levels in the connection's Permissions tab."
}
