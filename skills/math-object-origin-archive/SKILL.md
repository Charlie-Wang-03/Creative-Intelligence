---
name: math-object-origin-archive
description: Generate an evidence-based origin archive for one mathematical concept or object from supplied materials and, when needed, additional research. Use when the deliverable must follow the archive format supplied by the runner; do not use for ordinary definitions or proof-only tasks.
compatibility: Works with Moonshine runtimes that provide local file reading, skill loading, and optional live-search tools.
allowed-tools: read_runtime_file query_memory search_knowledge load_skill_definition verify_math_object_origin_archive
metadata:
  title: Mathematical Object Origin Archive
  category: research
  tags: mathematics, history, archive
  skill-standard: agentskills.io/v1
---

# Mathematical Object Origin Archive

## Usage Hint

- Use this skill to prepare an origin archive for exactly one mathematical object.
- Use it when local materials may need to be combined with targeted historical or mathematical research.

## Summary

- Produce a professional Markdown archive grounded in the supplied materials and identifiable sources.
- Follow the active format requirements supplied by the runner. The canonical source specification is `math-object-origin-archive/archive-format-specification.md`.

## Execution Steps

1. Identify the single target object, its standard name, mathematical scope, and nearby objects that must not be conflated with it.
2. Read the active format requirements and every supplied material before drafting.
3. Assess whether the supplied materials adequately support all mathematical and historical content required by the active format specification. Search additional sources only where material gaps remain.
4. Prefer original mathematical works and reliable scholarly sources for important historical claims. Use general summaries mainly to locate stronger sources.
5. Distinguish mathematical facts, documented historical facts, and synthesis or interpretation. Qualify claims when the evidence is incomplete or disputed.
6. Draft the archive according to the active format specification.
7. Prepare a concise historical-evidence note that pairs each important historical claim with its source and a short explanation of what the source supports.
8. Load `$verify-math-object-origin-archive` and submit the complete draft and historical-evidence note to the verification gate.

## Tool Calls

- `read_runtime_file`: Read the format specification and all supplied local materials.
- `query_memory`: Recover relevant work from the same object project or session when needed.
- `search_knowledge`: Reuse stable stored mathematical conclusions when they materially support the archive.
- `load_skill_definition`: Load the verification skill before final acceptance.
- `verify_math_object_origin_archive`: Submit the complete archive and historical evidence to the runner-provided verification gate.
- An enabled live-search or source-extraction tool: Fill material evidence gaps when local sources are insufficient.

## File References

- `math-object-origin-archive/archive-format-specification.md`: Canonical archive format and writing requirements.
- Runtime paths for the source materials supplied with the current object task.

## Output Contract

- Produce one complete Markdown archive for the named mathematical object.
- Keep the archive consistent with `math-object-origin-archive/archive-format-specification.md` and the active requirements supplied by the runner.
- Provide the complete archive and a concise historical-evidence note to the verification skill.
- Treat the archive as final only after the verification tool returns `passed=true`.

## Notes

- Do not force the object's development into a single-inventor or single-date account when the evidence shows precursors, parallel development, or gradual stabilization.
