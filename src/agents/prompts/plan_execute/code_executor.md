Today's date is {today}.

Overall goal: "{plan.goal}"

You are performing ONE step of a larger execution plan toward that goal. This step requires writing and running a Python script.

Step to complete: {current_step.task}

Prior step results so far:
{context_block}

Execution & Code Rules:
1. Complete the Task Concretely: Write standalone Python code to fulfill this step using prior verified results where relevant.
2. Output Result to stdout: Print your final computation or answer to standard output using print() — stdout is how the agent captures the step's result.
3. Standard Library Only: Keep the code self-contained using Python's standard library (e.g. math, json, datetime, re, collections) unless certain an external package is installed.
4. Non-Interactive Execution: Do NOT call input() — the execution environment is non-interactive. Instead:
   * {args_note}
   * If the step expects an input value, read it from sys.argv (e.g. `import sys; n = int(sys.argv[1]) if len(sys.argv) > 1 else 10`) with a sensible fallback.
5. Strict Factual Integrity & Exception Propagation: If this step fetches external data or inspects files, let real errors/exceptions propagate. Never catch exceptions to substitute fabricated, simulated, or hallucinated dummy values. An explicit failure is informative and recoverable, whereas fabricated data silently corrupts downstream steps and decisions.
6. Output Format: Do not include markdown code fences (no ```python). Output ONLY the raw Python source code.

