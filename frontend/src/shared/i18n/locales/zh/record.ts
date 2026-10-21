/** 自上而下阅读的一行（features/record）。 */
import type { Messages } from "../en"

export const record: Messages["record"] = {
  columns: {
    keys: "键",
    name: "列",
    type: "类型",
    value: "值",
  },
  copied: "{name} 已复制",
  read_failed: "无法读取此行",
  no_row: "此处没有行",
  no_columns: "没有列",
  copy_value: "复制此值",
  navigation: "行导航",
  previous: "上一行",
  next: "下一行",
}
