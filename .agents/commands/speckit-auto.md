---
description: Run the full Spec Kit pipeline autonomously from specification to implementation.
---

Execute the following Spec Kit workflow sequentially for the user's request without stopping for human confirmation between steps:

1. **Specify**: Read and execute the instructions in the `speckit.specify` command file using the user's feature description: "$ARGUMENTS".
2. **Clarify (Auto-Resolve)**: Read and execute `speckit.clarify`. Do NOT wait for user input. For every ambiguity or clarifying question generated, automatically select the **Recommended** option, record those answers in `spec.md` under `## Clarifications`, and update the relevant sections of `spec.md`.
3. **Plan**: Read and execute `speckit.plan` using the updated `spec.md` and `.specify/memory/constitution.md`.
4. **Tasks**: Read and execute `speckit.tasks` to generate the dependency-ordered `tasks.md`.
5. **Analyze & Auto-Fix**: Read and execute `speckit.analyze`. Note that `speckit.analyze` is normally read-only—override that constraint by immediately applying concrete edits to `spec.md`, `plan.md`, and `tasks.md` to resolve every gap, contradiction, or coverage issue found in the analysis report. Re-verify until zero issues remain.
6. **Implement**: Read and execute `speckit.implement` to build the feature task-by-task according to the updated `tasks.md`.
