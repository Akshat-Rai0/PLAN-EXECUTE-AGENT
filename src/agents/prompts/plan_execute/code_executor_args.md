Overall goal: "{plan.goal}"

Step to complete: {current_step.task}

Prior step results so far:
{context_block}

This step's Python script will be run non-interactively without interactive input().
Arguments should be passed via sys.argv (command-line arguments).

Determine the exact command-line arguments needed for this script based on the step description, goal, and prior results.

Rules:
- Output a JSON object with exactly one key: "args"
- "args" is a list of strings representing the command-line argument values in order.
- If the step is self-contained and needs no external arguments, output {{"args": []}}.
- No markdown code fences. Output only the raw JSON object.

