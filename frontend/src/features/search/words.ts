/**
 * When the search may be asked (D200).
 *
 * The server refuses fewer characters with 422; asking it anyway would turn
 * every first key into a refusal on screen.
 */
export const MIN_CHARACTERS = 2

/** How long typing must pause before the field asks. */
export const DEBOUNCE_MS = 150
