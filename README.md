# Spore Agent

可自我进化的智能助手。基于 CrewAI 框架，通过对话学习用户偏好，自动优化自身行为。

## 特性

- **双阶段架构**：Planner 规划 + Executor 执行，自动路由到最匹配的领域智能体
- **自我进化**：从对话中提取用户偏好，自动生成改进提案并应用
- **多智能体**：支持智能体裂变，高频领域自动分裂出专业子智能体
- **安全机制**：行为宪法约束 + 单快照回滚，进化不会失控

## 安装

```bash
pip3 install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple/ spore
```

或开发模式：

```bash
git clone https://github.com/SiriusCM/spore.git
cd spore
pip3 install -e .
```

## 配置

首次运行会在 `~/.spore/` 下生成 `.env` 配置文件，请填入你的 LLM API Key：

```bash
LLM_MODEL=MiniMax-M2.7
LLM_BASE_URL=http://ai-api.jdcloud.com/v1
LLM_API_KEY=your-api-key-here
```

## 使用

```bash
# 启动 Web 界面
spore web

# 进入控制台对话模式
spore cli

# 触发进化预览
spore evolve

# 触发进化并生效
spore evolve --apply

# 查看进化报告列表
spore reports
```

## 进化机制

双按钮流程：

1. **进化预览** - Evolver Agent 分析对话日志，识别用户纠正和偏好，生成提案
2. **应用进化** - 预览确认后执行：
   - 自动快照当前版本
   - 应用提案到 `script/` 目录
   - 语法校验 + import 冒烟测试
   - 失败自动回滚到上一版本

进化报告存入 SQLite 数据库，可随时查看。

## 项目结构

```
spore/
├── app.py              # CLI 入口
├── server.py           # Flask HTTP 服务
├── settings.py         # 配置管理
├── database.py         # SQLite 数据层
├── desktop.py          # PyQt 桌面应用
├── config/             # 静态资源配置
├── core/               # 框架核心（不可被进化修改）
│   ├── orchestrator.py # 编排器
│   ├── prompts.py      # 提示词模板
│   ├── chat_log.py     # 对话日志
│   ├── user_profile.py # 用户规则
│   └── registry/       # 注册表（Agent/Skill/Tool/MCP）
├── evolver/            # 进化引擎
│   ├── evolve.py       # 进化主逻辑
│   ├── proposals.py    # 提案工具
│   ├── applier.py      # 应用器
│   └── snapshot.py     # 快照管理
├── api/                # Flask API
│   ├── chat.py         # 聊天 & 进化触发
│   ├── evolve.py       # 进化报告 API
│   ├── skills.py       # Skill CRUD
│   ├── agents.py       # Agent CRUD
│   ├── mcp.py          # MCP 服务端管理
│   └── settings.py     # 设置 API
├── script/              # 可进化的提示词和工具
│   ├── prompts.py       # 可编辑的提示词
│   └── tools.py         # 可编辑的工具
└── view/               # Vue 3 前端
    ├── src/
    │   ├── App.vue      # 主界面
    │   ├── api.js       # API 封装
    │   ├── styles/      # 样式
    │   └── components/  # 弹窗组件
    └── package.json
```

## 前端开发

```bash
cd view
npm install
npm run build   # 构建到 view/dist/
```

## License

MIT