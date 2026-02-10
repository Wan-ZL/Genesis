# Stuck Incidents Log

This directory stores incident reports when agents get stuck.

Each incident file contains:
- Timestamp
- Agent name
- Last 100 lines of log
- Heartbeat state at time of detection
- Potential root cause analysis

These files are read by agents at the start of each iteration to learn from past failures.
