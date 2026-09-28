import { ref } from "vue"

/**
 * The page the guide window shows. Module state rather than a prop: there is
 * one guide window, and a second press of a Guide button turns the open one
 * to another page instead of opening a second window.
 */
export const shownGuidePage = ref("connections")
