# Hooks

已配置在 `~/.claude/settings.json`，所有项目生效。

## 当前配置的 Hooks

| Hook | 脚本 | 功能 |
|------|------|------|
| PostToolUse [*] | `2-PostToolUse-log-tools.sh` | 记录所有工具调用 |
| UserPromptSubmit | `5-UserPromptSubmit-remind-state.sh` | 提醒先读 state.md |
| SessionStart | `6-SessionStart-init.sh` | 初始化 session 日志 |
| Stop | `8-Stop-trigger-next.sh` | 自动触发下一轮迭代 |
| PreCompact | `10-PreCompact-save-context.sh` | 压缩前保存上下文 |

## 日志输出位置

所有日志写入 `/Users/zelin/Startups/Genesis/claude_iteration/runlog/`:
- `session-YYYY-MM-DD.log` - session 启动记录
- `tool-usage-YYYY-MM-DD.log` - 工具调用记录
- `YYYY-MM-DD_HHMM.md` - 每次 Stop 时的 runlog
- `pre-compact-*.log` - 压缩前的上下文记录

## 配置文件位置

- User level: `~/.claude/settings.json`
- Project level: `.claude/settings.json` (可选，会覆盖 user level)

## 测试 Hook

```bash
# 测试 PostToolUse 日志
echo '{"tool_name":"Bash"}' | bash hooks/2-PostToolUse-log-tools.sh
```

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
