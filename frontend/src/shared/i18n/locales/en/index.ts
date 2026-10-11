/**
 * The interface in English: the source every other language is typed against
 * (D224). A key missing from another language, or one it has and this does
 * not, fails `bun run type-check`.
 *
 * One module per area, so an area moves over without touching another's
 * file; `common` is only for words that mean the same thing wherever they
 * stand.
 */
import { auth, common, language, theme } from "./app"
import { catalog } from "./catalog"
import { kit } from "./kit"
import { layout } from "./layout"
import { preferences } from "./preferences"
import { workspace } from "./workspace"

export const en = { common, language, auth, theme, preferences, workspace, layout, catalog, kit }

export type Messages = typeof en
