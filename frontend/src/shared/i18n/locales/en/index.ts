/**
 * The interface in English: the source every other language is typed against
 * (D224). A key missing from another language, or one it has and this does
 * not, fails `bun run type-check`.
 *
 * One module per area, so an area moves over without touching another's
 * file; `common` is only for words that mean the same thing wherever they
 * stand.
 */
import { ai } from "./ai"
import { auth, common, language, theme } from "./app"
import { catalog } from "./catalog"
import { connectors } from "./connectors"
import { content } from "./content"
import { dashboards } from "./dashboards"
import { grid } from "./grid"
import { hypertable_design } from "./hypertable_design"
import { kit } from "./kit"
import { layout } from "./layout"
import { pipelines } from "./pipelines"
import { preferences } from "./preferences"
import { queries } from "./queries"
import { servers } from "./servers"
import { services } from "./services"
import { ssh_keys } from "./ssh_keys"
import { structure } from "./structure"
import { table_design } from "./table_design"
import { workspace } from "./workspace"

export const en = { common, language, auth, theme, preferences, workspace, layout, catalog, kit, grid, dashboards, ai, content, queries, connectors, servers, ssh_keys, table_design, hypertable_design, structure, pipelines, services }

export type Messages = typeof en
