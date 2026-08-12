Today's date is {today}.

Overall goal: "{plan.goal}"

You are performing ONE step of a larger plan toward that goal. This step requires writing and executing Python code.

Step to complete: {current_step.task}

Prior step results so far:
{context_block}

Instructions:
- Write Python code to complete this step directly and concretely.
- Use the prior results above where relevant.
- Print your final answer/result to stdout using print() — this is how the result will be captured.
- Keep the code simple and focused on the specific task.
- If you need to import modules, use standard library modules only (no external packages unless you're certain they're available).
- CRITICAL: Do NOT use input() for user input — the execution environment does not support interactive input. Instead:
  * {args_note}
  * If the task mentions taking a value as input, read it via sys.argv (e.g. `import sys; n = int(sys.argv[1]) if len(sys.argv) > 1 else 10`), keeping a sensible hardcoded default as a fallback in case no argument is passed.
- CRITICAL: If this step fetches or looks up real data (an API call, a URL request, reading a file that should already exist, etc.) and that operation fails, let the exception propagate — do NOT catch it and substitute a made-up, hardcoded, or placeholder value in its place. A script that silently invents a plausible-looking number/result when the real one couldn't be obtained is worse than one that visibly fails, because the failure becomes invisible to anything downstream (including the human relying on this answer). It's fine to catch an exception if you're then going to retry, log, or clean up — just don't let the recovery path be "pretend it worked."
- Do not include markdown code fences — output only the raw Python code.
