# Starfish Agent

可自我进化的智能 CLI 助手。基于 CrewAI 框架，通过对话学习用户偏好，自动优化自身行为。

## 特性

- **双阶段架构**：Planner 规划 + Executor 执行，自动路由到最匹配的领域智能体
- **自我进化**：从对话中提取用户偏好，自动生成改进提案并应用
- **多智能体**：支持智能体裂变，高频领域自动分裂出专业子智能体
- **安全机制**：行为宪法约束 + 快照回滚，进化不会失控

## 安装

```bash
pip install starfish-agent
```

## 配置

首次运行会在 `~/.starfish/` 下生成 `.env` 配置文件，请填入你的 LLM API Key：

```bash
LLM_MODEL=MiniMax-M2.7
LLM_BASE_URL=http://ai-api.jdcloud.com/v1
LLM_API_KEY=your-api-key-here
```

## 使用

```bash
# 进入对话模式
starfish

# 触发进化（预览）
starfish evolve

# 触发进化并生效
starfish evolve --apply

# 查看快照
starfish snapshots

# 回滚到指定快照
starfish rollback [tag]

# 重置 script 为初始版本
starfish reset
```

## 进化机制

每次对话后，Executor 会自动生成进化摘要。运行 `starfish evolve` 时：

1. Evolver Agent 分析对话日志，识别用户纠正和偏好
2. 生成提案（修改提示词 / 添加规则 / 创建工具 / 裂变智能体）
3. 语法校验 + import 冒烟测试，失败自动回滚

## 项目结构

```
starfish/
├── app.py          # CLI 入口
├── server.py       # Flask HTTP 服务
├── settings.py     # 配置管理
├── database.py     # SQLite 数据层
├── assets/        # PyQt 桌面图标等静态资源
├── core/          # 框架核心（不可被进化修改）
├── evolver/        # 进化引擎
├── vue/            # Vue 3 前端源码（npm install && npm run build）
└── script/         # 可进化的提示词和工具
```

## License

MIT

---

## 前端（Vue 工程）

前端源码在 `vue/` 目录，使用 Vue 3 + Element Plus 构建界面（聊天、控制面板、弹窗管理等）。

### 目录结构

```
vue/
├── index.html              入口
├── package.json
├── vite.config.js
├── .gitignore              （node_modules / dist 不入库）
└── src/
    ├── main.js             Vue 入口 + Element Plus 注册
    ├── api.js              所有后端 API 封装
    ├── App.vue             主界面（聊天 / 控制面板 / 头部按钮）
    ├── styles/main.css     全局样式
    └── components/
        ├── AppDialog.vue   通用弹窗壳：92vw / max 760px / max-height 70vh
        ├── SettingsDialog.vue
        ├── McpDialog.vue
        ├── SkillDialog.vue
        ├── AgentDialog.vue
        ├── PromptDialog.vue
        └── ToolsDialog.vue 内置工具秒开 + MCP 异步轮询
```

### 首次拉取代码后

```bash
cd vue
npm install        # 安装依赖（node_modules，已在 .gitignore）
npm run build      # 生成产物到 vue/dist/（已在 .gitignore）
```

### 开发模式（热更新）

```bash
# 终端 1：启动后端
python3 server.py

# 终端 2：启动 Vite dev server
cd vue
npm run dev               # http://localhost:5173
# /api/* 自动代理到 http://127.0.0.1:8765
```

### 静态资源说明

Flask 的 `static_folder` 指向 `vue/dist`，根路径 `/` 返回构建产物的 `index.html`。
`assets/icon.png` 是 PyQt 桌面应用的窗口图标，与前端构建无关，保留在原位。