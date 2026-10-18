/** Referenzen, die jemand zwischen zwei Spalten gezeichnet hat (features/declared). */
import type { Messages } from "../en"

export const declared: Messages["declared"] = {
  title: "Deklarierte Referenzen",
  declare_one: "Eine Referenz deklarieren",
  read_failed: "Die von diesem Knoten gezeichneten Referenzen konnten nicht gelesen werden",
  none: "Keine",
  remove_tooltip: "Diese Referenz entfernen",
  remove: {
    title: "Diese Referenz entfernen?",
    message: "Der Übergang {from} → {to} wird hier und am anderen Ende nicht mehr angeboten. Keine der Quellen wird geändert.",
    confirm: "Entfernen",
    done: "Deklarierte Referenz entfernt",
    failed: "Diese Referenz konnte nicht entfernt werden",
  },
  dialog: {
    subtitle: "Von einer Spalte von „{node}“ zu einer Spalte an beliebiger anderer Stelle",
    near: "Diese Spalte",
    points_at: "Verweist auf",
    far: "Jene Spalte",
    declare: "Deklarieren",
    read_failed: "Dieser Knoten konnte nicht als Zeilen gelesen werden",
    failed: "Diese Referenz konnte nicht deklariert werden",
  },
}
