/** Semantic names for shared controls. Values stay in the bundled Material Icons font. */
export const appIcons = {
  accountMenu: "account_circle",
  administration: "admin_panel_settings",
  close: "close",
  copy: "content_copy",
  enterFullscreen: "fullscreen",
  exitFullscreen: "fullscreen_exit",
  lightTheme: "light_mode",
  darkTheme: "dark_mode",
  createSshKey: "add",
  deleteSshKey: "delete_outline",
  importSshKey: "upload",
  preferences: "tune",
  signOut: "logout",
  sshKey: "key",
  lockSshKey: "lock",
  unlockSshKey: "lock_open",
  window: "web_asset",
} as const

/** The comparison font dropped this older Material Icons ligature. */
export function symbolComparisonIcon(icon: string): string {
  return icon === appIcons.deleteSshKey ? "delete" : icon
}
