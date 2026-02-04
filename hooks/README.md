# Hooks

已配置在 `~/.claude/settings.json`，所有项目生效。

## 当前配置的 Hooks

| Hook | 脚本 | 功能 |
|------|------|------|
| UserPromptSubmit | `5-UserPromptSubmit-remind-state.sh` | 提醒先读 state.md |
| SessionStart | `6-SessionStart-init.sh` | 初始化 session 日志 |
| Stop | `8-SessionEnd-trigger-next.sh` | 自动触发下一轮迭代 |

## 日志输出位置

所有日志写入 `$GENESIS_DIR/claude_iteration/runlog/` (project root):
- `session-YYYY-MM-DD.log` - session 启动记录
- `YYYY-MM-DD_HHMM.md` - 每次 Stop 时的 runlog

## 配置文件位置

- User level: `~/.claude/settings.json`
- Project level: `.claude/settings.json` (可选，会覆盖 user level)

## Hook 配置结构

```json
{
  "hooks": {
    "EventName": [
      {
        "matcher": "ToolName",  // 可选，仅部分事件需要
        "hooks": [
          {
            "type": "command",
            "command": "path/to/script.sh"
          }
        ]
      }
    ]
  }
}
```

## 多 Agent 系统

推荐使用 `./start-multi-agent-loop.sh` 来协调 Builder、Criticizer 和 Planner。

详见 `.claude/rules/08-multi-agent-system.md`。
