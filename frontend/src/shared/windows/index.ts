/**
 * Floating windows over the application.
 *
 * Not modal: several are open at once, so one can be read while another is
 * filled in. The engine knows nothing about what a window holds — a feature
 * supplies an id, a size, a look and a component, the same split that keeps
 * `shared/workspace` free of any knowledge about panels.
 */
export { default as WindowHost } from "./WindowHost.vue"
export { default as WindowDialog } from "./WindowDialog.vue"
export { provideWindows, useWindowManager, useWindows, windowsApiKey, windowsKey } from "./useWindows"
export type { OpenWindow, WindowAction, WindowLook, WindowsApi, WindowsContext, WindowState } from "./useWindows"
export { confirmInWindow, deleteWindowPreset, questionWindowPreset } from "./presets"
export type { ConfirmRequest } from "./presets"
export { openAsTabAction } from "./asTab"
export { bringToFront, CASCADE_STEP, clamp, fit, GRAB_MARGIN, place, resize, resizeTo } from "./geometry"
export type { Rect, ResizeEdge, Size } from "./geometry"
