# Performance Baseline Documentation

Generated: 2026-02-04

This document records baseline performance numbers for critical paths in the AI Assistant.
These baselines are used for regression detection (>20% threshold).

## Summary

| Category | Benchmark | Mean | Threshold (20%) |
|----------|-----------|------|-----------------|
| Tool Registry | Tool lookup | ~0.1ms | 0.12ms |
| Tool Registry | Tool lookup (miss) | ~0.1ms | 0.12ms |
| Tool Registry | List all tools | ~0.2ms | 0.24ms |
| Tool Registry | To OpenAI format | ~1.5ms | 1.8ms |
| Tool Registry | To Claude format | ~1.3ms | 1.6ms |
| Chat API | Message parsing | ~0.6ms | 0.72ms |
| Chat API | Response serialization | ~3ms | 3.6ms |
| Chat API | Full request (mocked) | ~3ms | 3.6ms |
| Memory | Add message | ~0.7ms | 0.84ms |
| Memory | Add 10 messages bulk | ~6.7ms | 8ms |
| Memory | Get messages (20) | ~0.5ms | 0.6ms |
| Memory | Get messages (200) | ~0.5ms | 0.6ms |
| Memory | Search (50 messages) | ~0.32ms | 0.38ms |
| Memory | Search (500 messages) | ~0.35ms | 0.42ms |
| Settings | Get setting | ~0.25ms | 0.3ms |
| Settings | Set setting | ~0.43ms | 0.52ms |
| File I/O | Write 1KB | ~0.015ms | 0.018ms |
| File I/O | Write 1MB | ~0.6ms | 0.72ms |
| File I/O | List 20 files | ~0.06ms | 0.072ms |
| File I/O | List 100 files | ~0.07ms | 0.084ms |

## Critical Path Details

### Tool Registry (Fastest Operations)

These are the fastest operations and most frequently called:

- **Tool lookup**: ~99ns mean (hash table lookup)
- **Tool lookup miss**: ~100ns mean
- **List all tools**: ~182ns mean (dictionary iteration)

### Memory Service (SQLite Operations)

Database operations are slower but still fast enough for interactive use:

- **Add message**: ~700µs mean (INSERT + UPDATE)
- **Get messages (20 msg)**: ~493µs mean (SELECT with JOIN)
- **Get messages (200 msg)**: ~544µs mean (scales well)
- **Search (500 msg)**: ~345µs mean (LIKE query)

### Settings Service

Settings operations hit the database:

- **Get setting**: ~250µs mean
- **Set setting**: ~435µs mean
- **Get all settings**: ~247µs mean

### File I/O

File operations depend heavily on disk speed:

- **Write 1KB**: ~15µs mean
- **Write 100KB**: ~34µs mean
- **Write 1MB**: ~634µs mean
- **Read + base64 encode**: ~37µs mean (10KB)

## Interpreting Results

- **Regression threshold**: 20% slower than baseline
- **Improvement**: More than 10% faster than baseline
- **Stable**: Within ±10% of baseline

## Running Benchmarks

```bash
cd assistant

# Run all benchmarks
python -m benchmarks

# Run with baseline comparison
python -m benchmarks --compare

# Save new baseline
python -m benchmarks --save-baseline

# CI mode (fails on regression)
python -m benchmarks --ci --threshold 20
```

## Notes

- Benchmarks use in-memory SQLite for consistent results
- File I/O uses temporary directories (SSD-like performance)
- Tool registry benchmarks use a populated registry (20 tools)
- Memory benchmarks pre-populate data before measuring
