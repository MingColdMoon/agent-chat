# 数据中台

与 langchain-agent 并列的独立数据工作台，共用原项目的 PostgreSQL、Redis、用户账号和 JWT 配置。

## 功能

- **数据接入**：读取 Agent Chat 的智能体、会话、消息、附件、消息附件和 RAG 分片表；源表按当前账号权限筛选。支持手动上传 CSV 和 JSON。导入前可以编辑数据集名称、目标表名、字段名、字段类型、是否导入及预览单元格。
- **数据分析**：查看导入数据的表格预览和全表字段画像，并通过类似 Agent Chat 的多轮对话分析数据。支持演示模式和 OpenAI 兼容模型。
- 导入数据保存到共享 PostgreSQL 中 dp_ 前缀的独立表；数据集按所有者隔离。每次最多导入 5,000 行，文件最大 20 MB。

## Docker 启动

在 langchain-agent 项目根目录启动数据库、Redis、Agent Chat 后端和数据中台服务：

    docker compose up -d --build postgres redis backend frontend data-platform-backend data-platform-frontend

- 数据中台：http://localhost:18081
- 数据中台 API 健康检查：http://localhost:8001/api/health
- Agent Chat：http://localhost:18080

使用 Agent Chat 已有账号登录即可。新注册账号也会写入共享 users 表。模型服务商、API Key、API 地址和模型名可在数据分析页面设置；API Key 仅保存在当前浏览器标签页。

## 本地开发

先在 langchain-agent 项目根目录启动 PostgreSQL、Redis 和 Agent Chat 后端，以创建并初始化共享表结构：

    docker compose up -d postgres redis backend

数据中台后端从 DATABASE_URL、REDIS_URL 和 JWT_SECRET 读取连接与登录配置，默认指向本地 Agent Chat 数据库。

后端进入 data-platform/backend：

    uv sync
    uv run uvicorn app.main:app --reload --port 8001

前端进入 data-platform/frontend：

    npm ci
    npm run dev

Vite 默认监听 5173，并将 /api 转发到 http://127.0.0.1:8001。

## 数据与导入规则

- 源表列表只包含 Agent Chat 的业务表，不暴露 users 密码表或数据中台管理表。
- 智能体只显示内置智能体和当前用户创建的智能体；会话相关表按用户隔离。
- 目标表名必须以 dp_ 开头；重复表名、非法字段名、重复字段名和类型转换失败都会拒绝导入。建表、写入行和登记数据集元数据在同一个事务内完成。
- 数据分析模型只接收全表字段画像和最多 30 行样本，不执行模型生成的 SQL。演示模式也会计算真实全表统计。
- 删除数据集会同时删除对应目标表和该数据集的对话记录。
