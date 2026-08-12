Overall goal: "{plan.goal}"

Step to complete: {current_step.task}

Prior step results so far:
{context_block}

This step's Python script will be run non-interactively — it cannot call input().
If it needs, it should read values from sys.argv (command-line arguments) instead.

Decide what command-line argument values (if any) this script needs, based on
the step description and prior results. For example, if the step says "print
the first 20 Fibonacci numbers", the script needs one argument: "20".

Rules:
- Output a JSON object with exactly one key: "args"
- "args" is a list of strings — the command-line argument values, in order.
- If the step doesn't need any input values (e.g. it's self-contained), output {{"args": []}}.
- No markdown fences around the JSON. Output only the raw JSON object.
