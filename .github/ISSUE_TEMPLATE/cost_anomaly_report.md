---
name: Cost Anomaly Report
about: Report a false positive or missed anomaly in cost detection
title: "[Anomaly] "
labels: anomaly-detection
assignees: ''
---

## Anomaly type

- [ ] False positive (flagged as anomaly but wasn't)
- [ ] Missed anomaly (should have been flagged but wasn't)
- [ ] Incorrect cost calculation

## Environment

- **forecost version**: (run `forecost --version`)
- **Model**: (e.g., gpt-4o, claude-3-5-sonnet-latest)
- **Provider**: (e.g., OpenAI, Anthropic)

## What happened?

Describe the anomaly detection behavior you observed.

## Expected behavior

What the correct detection/calculation should have been.

## Data

If possible, share:
- Output of `forecost forecast --json` 
- Output of `forecost status` 
- Relevant lines from `forecost track` 
