#!/bin/bash
# Hook: UserPromptSubmit (5)
# Purpose: Output reminder as additionalContext

# Output JSON that adds context to the conversation
cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "REMINDER: First read agent/state.md to understand current focus, then check GitHub Issues for priority work."
  }
}
EOF

exit 0
