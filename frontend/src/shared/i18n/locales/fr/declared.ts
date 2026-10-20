/** Références tracées par une personne entre deux colonnes (features/declared). */
import type { Messages } from "../en"

export const declared: Messages["declared"] = {
  title: "Références déclarées",
  declare_one: "Déclarer une référence",
  read_failed: "Les références tracées depuis ce nœud n'ont pas pu être lues",
  none: "Aucune",
  remove_tooltip: "Supprimer cette référence",
  remove: {
    title: "Supprimer cette référence ?",
    message: "Le passage {from} → {to} n'est plus proposé ici ni à l'autre extrémité. Aucune des sources n'est modifiée.",
    confirm: "Supprimer",
    done: "Référence déclarée supprimée",
    failed: "Cette référence n'a pas pu être supprimée",
  },
  dialog: {
    subtitle: "D'une colonne de « {node} » vers une colonne n'importe où ailleurs",
    near: "Cette colonne",
    points_at: "Pointe vers",
    far: "Cette colonne-là",
    declare: "Déclarer",
    read_failed: "Ce nœud n'a pas pu être lu comme des lignes",
    failed: "Cette référence n'a pas pu être déclarée",
  },
}
