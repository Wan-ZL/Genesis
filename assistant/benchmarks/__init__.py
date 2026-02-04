"""
Performance Benchmark Suite for AI Assistant

This package contains benchmarks for critical paths as specified in Issue #7:
1. Chat API response time (without LLM call - mock)
2. Memory service: add_message, get_messages, search_messages
3. Tool registry: lookup, execution time
4. Settings service: load, save
5. File upload: small (1KB), medium (1MB)
"""
