import type { Messages } from "../en"
import { ai } from "./ai"
import { auth, common, language, theme } from "./app"
import { catalog } from "./catalog"
import { content } from "./content"
import { dashboards } from "./dashboards"
import { grid } from "./grid"
import { kit } from "./kit"
import { layout } from "./layout"
import { preferences } from "./preferences"
import { queries } from "./queries"
import { workspace } from "./workspace"

export { problems } from "./problems"

export const messages: Messages = { common, language, auth, theme, preferences, workspace, layout, catalog, kit, grid, dashboards, ai, content, queries }
