# Acknowledgements

slim-agent draws inspiration and design patterns from the following projects:

- **[obra/superpowers](https://github.com/obra/superpowers)** — Evidence Over Claims, systematic debugging, two-stage review, parallel dispatch, skill-auto-trigger patterns
- **[anthropic-experimental/academic-research-skills](https://github.com/anthropic-experimental/academic-research-skills)** — Material Passport (append-only + hash chain), Anti-Patterns, Pre-commitment Prompt, Citation Hallucination classification, Checkpoint FULL/SLIM/MANDATORY
- **[tinyhumansai/openhuman](https://github.com/tinyhumansai/openhuman)** — Grapheme-aware text processing, atomic write pattern, cwd-jail sandbox, rule engine 3-layer loading, TokenJuice text compression
- **[Nous Research / hermes-agent](https://github.com/NousResearch/Hermes-Agent)** — Footprint Ladder (L1-L6 capability tiering), model-tool cost awareness

Design principles adopted (no code copied; license terms respected):
- Copilot Not Pilot — AI assists, human decides
- Evidence Over Claims — verify before declaring done
- Diff-Patch — surgical replacement, not full rewrite
- Footprint Ladder — minimal footprint capability integration
