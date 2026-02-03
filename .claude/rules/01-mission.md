# Mission Rules

## Primary Mission
Build a self-evolving, always-on AI assistant that:
1. Runs 24/7 on the user's Mac mini
2. Maintains persistent memory across all interactions
3. Can create, test, and use tools autonomously
4. Supports multimodal input (text, images, PDFs)
5. Evolves through iterative Claude Code runs

## Success Criteria
- User can interact with the assistant via a simple web UI
- Assistant remembers context from previous conversations
- System can be triggered to improve itself via GitHub Issues
- All changes are logged, tested, and reviewable

## Constraints
- Must work offline-first (Mac mini local deployment)
- Must never lose important context (persistent memory in repo)
- Must be auditable (all runs logged, all changes in git)
