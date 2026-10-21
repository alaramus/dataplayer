/** 数据有多旧，多久刷新一次（shared/freshness）。 */
import type { Messages } from "../en"

export const freshness: Messages["freshness"] = {
  live: "实时",
  nothing: "无",
  read_now: "刚刚从数据源读取。",
  read_ago: "已于 {age} 前从数据源读取。",
  keeps_as_source_says: "此连接会按数据源声明的时间保留响应。",
  keeps_nothing: "此连接不保留任何内容：每次读取都会到达数据源。",
  keeps_for: "此连接会保留响应 {window}。",
}
