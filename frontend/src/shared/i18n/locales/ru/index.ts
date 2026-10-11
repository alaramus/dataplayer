import type { Messages } from "../en"
import { auth, common, language, theme } from "./app"
import { catalog } from "./catalog"
import { kit } from "./kit"
import { layout } from "./layout"
import { preferences } from "./preferences"
import { workspace } from "./workspace"

export { problems } from "./problems"

export const messages: Messages = { common, language, auth, theme, preferences, workspace, layout, catalog, kit }
