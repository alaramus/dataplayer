import { ref } from "vue"

/**
 * The page the Help Center shows. Module state rather than a prop: there is
 * one guide window, and a second press of a Guide button turns the open one
 * to another page instead of opening a second window. Opened from the user
 * menu or F1 it stays on the page last read, the overview at first.
 */
export const shownGuidePage = ref("overview")
