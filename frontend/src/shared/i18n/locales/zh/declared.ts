/** 有人在两列之间绘制的引用（features/declared）。 */
import type { Messages } from "../en"

export const declared: Messages["declared"] = {
  title: "声明引用",
  declare_one: "声明一个引用",
  read_failed: "无法读取从此节点绘制的引用",
  none: "无",
  remove_tooltip: "移除此引用",
  remove: {
    title: "移除此引用？",
    message: "{from} → {to} 将不再在此处及另一端提供。两个数据源都不会被更改。",
    confirm: "移除",
    done: "声明引用已移除",
    failed: "无法移除此引用",
  },
  dialog: {
    subtitle: "从 {node} 的一列到其他任意位置的一列",
    near: "此列",
    points_at: "指向",
    far: "那一列",
    declare: "声明",
    read_failed: "无法将此节点作为行读取",
    failed: "无法声明此引用",
  },
}
