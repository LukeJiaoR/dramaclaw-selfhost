# DramaClaw Selfhost Handover

更新时间：2026-08-18（Asia/Shanghai）

## 1. 当前结论

该工作区是 DramaClaw 的独立 selfhost 分支，已经包含可视化、可插拔的
Provider Hub，以及 AI 声线设计和人物声线提示词生成能力。代码已推送到公开仓库，
本地服务当前健康运行。创建本文档前，代码工作区无其他未提交修改。

项目不再嵌套在“视频生成管线”父仓库中。旧的独立
`DramaClawProviderHub` 目录已经停用并移入 macOS 废纸篓。

## 2. 仓库与远程

- 本地路径：`/Users/luke/WorkSpace/dramaclaw-selfhost`
- 公开仓库：<https://github.com/LukeJiaoR/dramaclaw-selfhost>
- 当前分支：`main`
- 当前提交：`664668d feat: add pluggable selfhost provider and AI voice workflows`
- `origin`：`git@github.com:LukeJiaoR/dramaclaw-selfhost.git`
- `upstream`：`https://github.com/dramaclaw/dramaclaw.git`

`origin` 用于本项目提交，`upstream` 仅用于同步官方 DramaClaw 更新。不要把本项目
改动推送到 `upstream`。

本机仓库使用 `.ai-gh-account` 将 GitHub CLI 路由到 `LukeJiaoR`。该文件只保留在
`.git/info/exclude`，不可提交。执行 GitHub 写操作前先运行：

```bash
gh ai-account
gh api user --jq .login
```

两者应指向 `LukeJiaoR`。不要使用 `gh auth switch`。

## 3. 当前运行服务

| 服务 | 地址 | Compose 项目 | 当前状态 |
| --- | --- | --- | --- |
| DramaClaw Web | `http://localhost:19080` | `dramaclaw` | 运行中 |
| DramaClaw API | `http://localhost:19780` | `dramaclaw` | healthy |
| Provider Hub | `http://localhost:18001` | `dramaclawproviderhub` | healthy |
| NewAPI | `http://localhost:13000` | `dramaclaw` | healthy |

DramaClaw 当前由以下命令启动，固定 `-p dramaclaw` 是为了继续复用原数据卷：

```bash
cd /Users/luke/WorkSpace/dramaclaw-selfhost
docker compose -p dramaclaw \
  -f docker-compose.selfhosted.yml \
  -f docker-compose.yml up -d
```

Provider Hub 从仓库内置目录运行：

```bash
cd /Users/luke/WorkSpace/dramaclaw-selfhost/provider-hub
docker compose -p dramaclawproviderhub up -d --build
```

停止服务时不要添加 `-v`，否则会删除持久化数据卷。

## 4. 架构与调用链

Provider Hub 是独立的适配层，DramaClaw 只依赖稳定的 OpenAI 兼容入口：

```text
DramaClaw
  -> http://host.docker.internal:18001/v1
  -> Provider Hub 路由/能力绑定
  -> OpenAI 兼容服务、MiMo、视频供应商或远程 ComfyUI
```

Provider Hub 的解析顺序为：

1. 精确的传入模型覆盖。
2. 能力绑定，例如 `text`、`embedding`、`image`、`video`、`tts`。
3. 该能力的默认启用服务。

Provider Hub 内置协议包括 `openai`、`openai_compatible`、
`openai_audio_speech`、`mimo_chat_audio`、`openai_video`、`volcengine_omni`、
`xai`、`veo3` 和 `comfyui_native`。适配器还可通过
`dramaclaw_provider_hub.adapters` Python entry point 外挂。

远程 ComfyUI 能力已保留。配置时 Base URL 应填写能够访问 `/prompt`、`/history`、
`/view` 和上传接口的 ComfyUI 服务根地址，通常与 ComfyUI Web 地址相同，但必须从
Provider Hub 容器可达。当前 Provider Hub 数据中未看到已启用的 ComfyUI 服务。

## 5. Provider 配置现状

Provider Hub 当前持久化状态：

- 8 个服务。
- 7 个能力绑定。
- 2 条精确模型路由。
- 服务覆盖本地 Qwen3 Embedding、文本、图片/分镜图片、MiMo TTS，以及火山引擎、
  Gemini Veo、xAI 视频链路。
- DramaClaw 项目内的角色图、身份图、场景图、道具图、分镜草图、渲染图和 Freezone
  默认统一走 `provider_hub_image`。文生图调用 `/v1/images/generations`，图生图调用
  `/v1/images/edits` 并以 multipart 直接上传参考图，不依赖 NewAPI 图片渠道或 OSS relay。
- 常规文本和视觉理解统一通过 Provider Hub `/v1/chat/completions`。功能模型设置在当前
  gateway 指向 Provider Hub 时，会直接同步 Hub service 与精确 model route；原
  `/custom/newapi/*` API 路径仅作为前后端兼容契约保留。
- DirectorWorld 的 Block World、master/reverse overlap、空间合同、草图视觉 gate 和
  视频提示词翻译均已改走 Provider Hub。显式 CLI key/base URL override 仍可用于独立调试。

本地 Qwen3 Embedding 0.6B 模型目录：

```text
/Users/luke/.cache/lm-studio/models/mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ
```

Provider 凭据只存在于本地持久化配置中，不在 Git 仓库内。管理 UI 返回的是脱敏状态，
不要在日志、测试 fixture、截图或文档中写入真实 Key。

## 6. 持久化数据

当前 Docker 数据卷：

- `dramaclaw_ce-data`：DramaClaw 设置、项目状态和生成数据。
- `dramaclaw_newapi-data`：现有 NewAPI 数据。
- `dramaclawproviderhub_provider-hub-data`：Provider Hub 的 `provider-hub.db`。

Provider Hub 切换目录时已经复用原卷，切换前后均为 8 个服务、7 个绑定、2 条路由。
不要把数据库文件复制进仓库，也不要直接删除上述卷。

旧 Provider Hub 目录的可恢复副本暂在：

```text
/Users/luke/.Trash/DramaClawProviderHub-old-20260818
```

该副本只剩虚拟环境、测试缓存、Playwright 记录和截图，没有 `.env`。确认不再需要后
可由用户清空废纸篓。

## 7. 已实现功能

### Provider Hub

- Provider、模型、能力绑定和精确路由均可通过管理 UI 修改。
- DramaClaw 逻辑模型名与真实上游模型解耦。
- 支持 MiMo Chat Audio、标准 OpenAI TTS、主流视频协议和原生 ComfyUI API workflow。
- 支持从 LocalMiniDrama 配置导入，重复导入保持幂等。
- 配置更新时空 Key 不会覆盖已保存的 Key。

### AI 声线

- 人物模型新增 `voice_prompt`，SQLite schema version 已升级到 2。
- `voice_prompt` 与人物提取、`face_prompt` 在同一次 LLM 结构化提取中生成。
- 再次“自动提取”会回填空的 `voice_prompt`，但保留用户已编辑内容。
- 人物和旁白面板均支持 AI 声线生成。
- 增加“AI 优化提示词”，用于生成或润色声线描述。
- 声线生成成功后保存最终采用的提示词。
- MiMo VoiceDesign 通过 Provider Hub 适配，不依赖 NewAPI 原生支持。
- 文本功能使用稳定的 `DC-*-LLM` 逻辑模型名；纯文本进入 `text` binding，带图请求进入
  `vision` binding。设置页保存逐功能映射时，会在 Provider Hub 创建对应精确路由。

关键实现位置：

- `provider-hub/src/provider_hub/`
- `src/novelvideo/voice_design.py`
- `src/novelvideo/api/routes/characters.py`
- `src/novelvideo/api/routes/projects.py`
- `src/novelvideo/cognee/pipeline.py`
- `src/novelvideo/sqlite_store.py`
- `frontend/src/components/assets/voice-design-dialog.tsx`

## 8. 验证记录

发布前已通过：

- DramaClaw 聚焦后端测试：65 passed。
- 前端声线相关测试：9 passed。
- Provider Hub 测试：10 passed。
- 合计：84 passed。
- TypeScript 检查、Ruff、`git diff --check` 和生产 Docker 构建均通过。
- Web、API、Provider Hub 健康检查均返回 HTTP 200。
- 已对提交内容检查常见 API Key、私钥、`.env`、数据库、日志和本地运行产物，未发现
  真实凭据被提交。

常用聚焦验证命令：

```bash
uv run pytest -q \
  tests/test_voice_design.py \
  tests/test_api_character_voice_samples.py \
  tests/test_narrator_main_semantics.py \
  tests/test_sqlite_schema_initialization.py \
  tests/test_sqlite_store.py

cd frontend
npm test -- --run \
  src/__tests__/components/assets/voice-design-dialog.test.tsx \
  src/__tests__/components/assets/character-voice-panel.test.tsx \
  src/__tests__/components/assets/narrator-voice-panel.test.tsx \
  src/__tests__/components/assets/narrator-voice-panel.ce.test.tsx

cd ../provider-hub
uv sync --extra dev
uv run pytest -q
```

## 9. 已知现状与后续建议

- 图片、文本与视觉理解已默认绕过 NewAPI，但当前 DramaClaw 启动方式仍保留
  `newapi` 容器，用于视频、音频和历史自定义配置兼容。不要删除 NewAPI 或其数据卷。
- 下一步适合增加一个正式的根级 Provider Hub Compose profile/override，将 Web、API 和
  Provider Hub 统一编排，并逐步淘汰当前同时叠加两个 Compose 文件的启动方式。
- 同步官方更新时先 `git fetch upstream`，在单独分支合并或 rebase，并重点检查
  Provider 配置、SQLite schema、人物提取结构和前端声线面板冲突。
- `provider-hub/.env`、数据库、浏览器产物、生成输出和本地模型不得提交。
- 页面上偶尔出现的账户头像 `404` 与 Provider/声线链路无关，是已知的非阻断控制台噪音。

## 10. 快速接手检查

```bash
cd /Users/luke/WorkSpace/dramaclaw-selfhost
git status --short --branch
git remote -v
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' \
  | rg 'dramaclaw|provider-hub'
curl -fsS http://127.0.0.1:19780/healthz
curl -fsS http://127.0.0.1:18001/healthz
```

预期 `main` 与 `origin/main` 一致，API 和 Provider Hub 为 healthy，且 Provider Hub
容器的 Compose working directory 是：

```text
/Users/luke/WorkSpace/dramaclaw-selfhost/provider-hub
```
