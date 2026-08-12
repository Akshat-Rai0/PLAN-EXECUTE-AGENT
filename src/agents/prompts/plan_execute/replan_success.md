

Context of completed steps (a recent step revealed new information):
{context_str}

A just-completed step has surfaced new information not anticipated by the original plan.
Your job is to OPTIMIZE the remaining steps by incorporating this new information.

Guidelines:
- Preserve the overall goal — do not change what the plan is trying to achieve.
- Eliminate steps that are now redundant given what was just learned (e.g., if a step
  was going to search for data that is already in the results above, drop it).
- Sharpen specificity of remaining search/research steps using concrete details now
  known (exact names, dates, IDs, URLs, etc.) rather than generic descriptions.
- Add any new steps that the new information implies are necessary to fully satisfy
  the goal (e.g., a follow-up search for a specific entity now identified).
- Keep only PENDING steps in the returned subtasks list — do not re-include DONE steps.
- Prefer fewer, more targeted steps over many broad ones.
- Do NOT include failure-recovery logic — all completed steps succeeded.

