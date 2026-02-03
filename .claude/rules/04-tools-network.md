# Tools + Network Rules

## Tooling philosophy
- Prefer building a tool when a task repeats 3+ times.
- Every tool must have:
  - interface spec
  - tests and/or evals
  - documentation
  - registry entry (if you create a registry)

## Network
- Network is unrestricted by domain, but:
  - all external calls must be logged (destination + purpose + summary)
  - never send secrets
  - never scrape or store private user data outside this repo

## Tool naming awareness
- MCP tool names are like: `mcp__server__tool`.
- Keep hooks matchers ready to target a whole server or tool family.
