/**
 * Floating windows over the application.
 *
 * Not modal: several are open at once, so one can be read while another is
 * filled in. The engine knows nothing about what a window holds — a feature
 * supplies an id, a size, a look and a component, the same split that keeps
 * `shared/workspace` free of any knowledge about panels.
 */
export { default as WindowHost } from "./WindowHost.vue"
export { useWindows, windowsKey } from "./useWindows"
export type { OpenWindow, WindowLook, WindowsApi, WindowsContext, WindowState } from "./useWindows"
export { bringToFront, CASCADE_STEP, clamp, GRAB_MARGIN, place } from "./geometry"
export type { Rect, Size } from "./geometry"
