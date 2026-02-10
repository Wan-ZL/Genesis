# Hooks

Genesis 项目专用 hooks，配置在 `.claude/settings.json`（项目级）。

## 当前配置的 Hooks

| Hook | 脚本 | 功能 |
|------|------|------|
| PostToolUse | `genesis-heartbeat.sh` | 心跳检测（自愈机制） |
| UserPromptSubmit | `5-UserPromptSubmit-remind-state.sh` | 提醒先读 state.md |
| SessionStart | `6-SessionStart-init.sh` | 初始化 session 日志 |

## 配置文件位置

| 位置 | 作用域 | 内容 |
|------|--------|------|
| `~/.claude/settings.json` | 全局 | 通用通知 hooks（完成通知、权限请求通知） |
| `.claude/settings.json` | 项目级 | Genesis 专用 hooks（心跳、状态提醒、日志初始化） |

## 自愈机制

心跳脚本 (`~/.local/bin/genesis-heartbeat.sh`) 在每次工具调用后更新心跳文件。
`start-multi-agent-loop.sh` 检测心跳超时（15分钟），自动终止卡住的 agent。

详见 `orchestrator/README.md`。

## 多 Agent 系统

使用 `./start-multi-agent-loop.sh` 来协调 Builder、Criticizer 和 Planner。

控制文件：`hooks/loop_multi_agent.txt`
- `true` = 继续循环
- `false` = 停止循环

详见 `.claude/rules/08-multi-agent-system.md`。
