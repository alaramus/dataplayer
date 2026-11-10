/** 欢迎导览（features/onboarding），以及用户指南窗口（features/guide）和朗读（features/speech）的少量文字。 */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "欢迎使用 DataPlayer",
  intro: "选择语言和应用的外观。",
  tour_offer: "然后进行三分钟的导览：你将创建一个小数据库、使用它，再把它清理掉，每个需要点击的按钮旁都有提示。",
  position: "第 {n} 步，共 {total} 步",
  finish: "完成",
  take_tour: "开始导览",
  look_around: "我自己看看",
  mark_failed: "无法将导览标记为已看过",
  close_title: "结束导览？",
  close_message: "导览不会再自动打开。你可以随时在偏好设置的“欢迎导览”中再次进行。",
  close_confirm: "结束导览",
  keep_going: "继续",
  end_tour: "结束导览",
  tour: {
    make: {
      title: "创建数据库",
      add: "按 + 添加连接。",
      pick: "选择 SQLite。",
      here: "SQLite 不需要服务器：直接在这里、在你自己的存储中创建数据库。",
      submit: "保留默认选项，即一个带示例数据的文件，然后创建。",
    },
    open: {
      title: "打开表",
      connection: "打开新连接以查看其中的表。",
      table: "打开 {table} 表。",
    },
    filter: {
      title: "筛选行",
      open: "打开筛选。",
      fill: "只显示被阻塞的任务：列 status，等于，blocked。然后应用。",
    },
    edit: {
      title: "修改值",
      cell: "双击任务标题即可修改。",
      save: "写一个新标题并保存。修改会直接写入数据库。",
    },
    query: {
      title: "运行查询",
      open: "将此表作为查询打开：控制台会得到为它写好的 SELECT。",
      run: "运行它。这里可以编写任意 SQL。",
    },
    disconnect: {
      title: "删除连接",
      edit: "打开连接的设置。",
      delete: "删除连接。",
      confirm: "确认。只删除连接：数据库文件仍保留在你的存储中。",
    },
    folder: {
      title: "连接你自己的文件夹",
      add: "再次按 +。",
      pick: "选择“文件”。",
      create: "创建连接。",
      save: "路径 / 就是你的全部个人存储。保存连接。",
    },
    find: {
      title: "找到文件",
      connection: "打开文件夹连接。",
      folder: "打开 {folder}：你创建的数据库就在那里。",
    },
    remove: {
      title: "删除文件",
      tick: "勾选 {file}。",
      actions: "打开操作菜单。",
      delete: "选择“删除”。",
      confirm: "确认。演示内容全部清除，文件夹连接仍归你所有。",
    },
    finished: {
      title: "你已掌握基础",
      text: "连接、表、筛选、编辑、查询以及你自己的存储。管道、仪表板和 AI 代理在左侧栏中。随时可在偏好设置中再次进行导览。",
    },
  },
  guide: {
    title: "用户指南",
    not_a_page: "该链接未指向用户指南中的页面",
    read_failed: "无法读取用户指南中的此页面",
  },
  speech: {
    listen: "朗读",
    stop: "停止朗读",
    browser_default: "浏览器默认",
  },
}
