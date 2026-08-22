import type { Page } from "@playwright/test"

/**
 * Finding a node of the catalog tree.
 *
 * The header text is not anchored: the custom header renders the icon first,
 * so the name of a node never starts the string.
 */
export function nodeHeader(page: Page, label: string) {
  return page.locator(".q-tree__node-header", { hasText: label }).first()
}

export function arrowFor(page: Page, label: string) {
  return nodeHeader(page, label).locator(".q-tree__arrow")
}
