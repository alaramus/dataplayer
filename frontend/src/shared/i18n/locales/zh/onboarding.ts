/** 欢迎导览（features/onboarding），以及用户指南窗口（features/guide）和朗读（features/speech）的少量文字。 */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "欢迎使用 DataPlayer",
  intro: "选择语言和应用的外观。",
  tour_offer: "然后进行三分钟的导览：你将创建一个小数据库、使用它，再把它清理掉，每个需要点击的按钮旁都有提示。",
  position: "第 {n} 步，共 {total} 步",
  finish: "完成",
  next: "下一步",
  take_tour: "开始导览",
  look_around: "我自己看看",
  mark_failed: "无法将导览标记为已看过",
  close_title: "结束导览？",
  close_message: "导览不会再自动打开。你可以随时在偏好设置的“导览”中再次进行。",
  close_confirm: "结束导览",
  keep_going: "继续",
  end_tour: "结束导览",
  more_tours: "查看更多导览",
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
    service: {
      title: "在这里启动的服务器",
      add: "再按一次 +。",
      pick: "选择 Redis：之前没有类似的东西。",
      start: "这个按钮会直接在这里用 Docker 启动 Redis，并附带试用数据，还会为你创建连接。此目录中带有这种按钮的任何服务器都能这样启动。导览到此结束：窗口交给你了。",
    },
  },
  tours: {
    basics: {
      title: "基础",
      summary: "创建数据库、使用它并将其清理。",
    },
    practice_name: "practice",
    folder_name: "我的文件",
    preparing: "正在为本导览创建练习数据库…",
    setup_failed: "导览无法准备练习数据库",
    cleanup_failed: "导览无法移除练习数据库",
    list: {
      take: "开始",
      again: "再来一次",
    },
    views: {
      title: "换种方式看表",
      summary: "同一张表以图表、结构和文档的形式呈现。",
      back: "回到 {table} 标签页。",
      open: {
        title: "打开练习表",
        connection: "这个练习数据库是导览创建的。打开它。",
        table: "打开 {table}。",
      },
      chart: {
        title: "作为图表",
        hint: "把这一页画成图表。",
      },
      structure: {
        title: "作为结构",
        hint: "查看表的列、键和索引。",
      },
      document: {
        title: "作为文档",
        hint: "以文档而不是表格的形式阅读行。",
      },
      closing: {
        title: "完成",
        text: "关闭此处后，练习数据库将被移除。",
      },
    },
    pipeline: {
      title: "管道",
      summary: "表中的行以 CSV 文件保存到你的文件夹。",
      new: {
        title: "新管道",
        space: "打开管道。",
        create: "创建一个新管道。",
      },
      source: {
        title: "行从哪里来",
        connection: "按练习数据库：它的表会在画布旁打开。",
        schema: "打开 main，SQLite 唯一的模式。",
        tick: "勾选 {table}。",
        done: "把它放到画布上。",
      },
      target: {
        title: "行到哪里去",
        connection: "现在按你的文件夹。",
        top: "勾选文件夹本身。",
        done: "把它放到画布上。",
      },
      link: {
        title: "连接它们",
        hint: "将 {table} 的行拖到文件夹的行上。可以放置的行会亮起。",
      },
      run: {
        title: "运行",
        menu: "打开“开启”旁边的菜单。",
        hint: "立即运行一次。连线会把表保存为 CSV 文件。",
        taken: "文件夹中已有同名文件：在“如果名称已被占用”中选择“两者都保留”，然后再运行一次。",
      },
      seen: {
        title: "文件",
        space: "回到“数据”。",
        folder: "打开你的文件夹。",
        file: "这就是管道生成的 CSV。结束时练习数据库会被移除，文件会保留。",
      },
    },
    dashboards: {
      title: "仪表板",
      summary: "仪表板在哪里创建，指标从哪里来。",
      space: {
        title: "仪表板",
        hint: "打开仪表板。",
      },
      new: {
        title: "一个仪表板",
        hint: "仪表板从这里开始：网格上的指标图表和磁贴。",
        store: "仪表板把指标保存在管理员在此处启动一次的存储中。",
      },
      agent: {
        title: "来自代理的指标",
        open: "打开指标来源。",
        view: "代理会上报其所在机器的指标。",
        register: "在这里注册代理：你会得到它的密钥和一个 Docker Compose 文件，用它在要监控的机器上启动代理。",
      },
      connections: {
        title: "你的连接的指标",
        view: "你的连接也可以上报自身的情况。",
        switch: "选择一个连接并打开：PostgreSQL、MySQL 和 Redis 会上报自身指标。",
      },
    },
    agent: {
      title: "AI 代理",
      summary: "在哪里选择代理的密钥、模型和上下文。",
      space: {
        title: "代理",
        hint: "打开 AI 空间。",
      },
      chat: {
        title: "聊天",
        hint: "开始新的聊天。",
        close: "关闭设置以返回聊天。",
      },
      key: {
        title: "密钥",
        open: "打开 AI 设置。",
        hint: "默认模型在这里选择，旁边是密钥按钮：代理使用你在某个提供商的密钥，例如 Anthropic、OpenAI 等。",
      },
      model: {
        title: "模型",
        hint: "选择聊天使用的模型。",
      },
      attach: {
        title: "它知道什么",
        hint: "附加一张表、一个标签页或一个节点：代理会读取你所指的内容，而不是猜测。",
      },
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
