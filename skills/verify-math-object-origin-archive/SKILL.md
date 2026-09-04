---
name: verify-math-object-origin-archive
description: Verify a complete mathematical-object origin archive for mathematical correctness, support for important historical claims, and compliance with the runner-defined archive format. Use as the acceptance gate for origin archives, not for proof-only verification.
compatibility: Requires the verify_math_object_origin_archive tool dynamically registered by the origin-archive runner.
allowed-tools: verify_math_object_origin_archive read_runtime_file query_memory search_knowledge
metadata:
  title: Verify Mathematical Object Origin Archive
  category: verification
  tags: mathematics, history, archive, verification
  skill-standard: agentskills.io/v1
---

# Verify Mathematical Object Origin Archive

## Usage Hint

- Use this skill when a complete mathematical-object origin archive is ready for final review.
- Use it only with the complete archive and the historical evidence actually used to prepare it.

## Summary

- Apply one fail-closed acceptance gate across mathematical accuracy, historical support, and format compliance.
- The runner supplies the authoritative object identity and format requirements directly; the model does not redefine or retransmit them.
- Accept the archive only when the verification tool returns `passed=true`.

## Execution Steps

1. Assemble the complete candidate archive and the concise historical-evidence note used to support its important historical claims.
2. Call `verify_math_object_origin_archive` with the complete archive and historical evidence.
3. Treat mathematical accuracy as passed only when definitions, distinctions, formulas, and substantive mathematical claims contain no material error.
4. Treat historical accuracy as passed only when important historical claims are supported by the supplied evidence or explicitly qualified.
5. Judge format compliance only against the complete authoritative specification injected by the runner. Do not add format requirements from this skill.
6. If any dimension is incorrect or inconclusive, revise the affected content and submit the complete revised archive again.
7. Stop only when the tool returns `passed=true`; never infer acceptance from explanatory prose.

## Tool Calls

- `verify_math_object_origin_archive`: Run the mathematical, historical, and format checks and return the acceptance result.
- `read_runtime_file`: Re-read a source or the canonical format specification when resolving a reported issue.
- `query_memory`: Recover a relevant earlier verification result from the same object session when necessary.
- `search_knowledge`: Check a stored mathematical conclusion used by the archive when necessary.

## File References

- `math-object-origin-archive/archive-format-specification.md`: Canonical format source used by the runner and format reviewer.
- Runtime paths for materials used in the candidate archive.

## Output Contract

- Return the structured result from `verify_math_object_origin_archive`.
- A passing result must report `passed=true`, no unresolved material issues, and the exact verified Markdown archive.
- A failing result must report repair targets and must not be represented as an accepted archive.

## Notes

- The historical review is evidence-bounded: plausibility or model memory alone does not establish an important historical claim.
- Any change to the archive invalidates the earlier accepted text and requires verification of the complete revised version.
