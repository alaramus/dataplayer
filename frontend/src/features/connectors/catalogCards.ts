import type { AdapterTypeInfo, ServiceTemplateInfo } from "@/client"

/**
 * The cards of the catalog of types. Plain functions, tested without mounting.
 *
 * A type is one card, or one for each product it speaks to when the server
 * says so — MySQL and MariaDB for `mysql` (D264). Every card of a type is the
 * type: it opens the same form and makes the same connection.
 */
export interface CatalogCard {
  /** Names the card, its picture and its test id; the type's name for a type of one card. */
  key: string
  type: AdapterTypeInfo
  title: string
  /** The services the card offers to start, or null for every one of its type. */
  templates: string[] | null
}

export function cardsOf(types: AdapterTypeInfo[]): CatalogCard[] {
  return types.flatMap((type): CatalogCard[] =>
    type.faces !== undefined && type.faces.length > 0
      ? type.faces.map((face) => ({ key: face.key, type, title: face.title, templates: face.templates }))
      : [{ key: type.name, type, title: type.title, templates: null }]
  )
}

/** The services of this card that this server offers to start. */
export function templatesOf(card: CatalogCard, startable: ServiceTemplateInfo[]): ServiceTemplateInfo[] {
  const ofType = startable.filter((offered) => offered.adapter_type === card.type.name)
  const wanted = card.templates
  return wanted === null ? ofType : ofType.filter((offered) => wanted.includes(offered.key))
}
