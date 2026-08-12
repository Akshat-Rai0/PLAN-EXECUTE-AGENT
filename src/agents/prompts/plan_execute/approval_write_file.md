You are determining what file to write for one step of a software task.

Today's date: {_prompt_today}
Overall goal: "{plan.goal}"

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Rules:
- Output a JSON object with exactly one key: "path"
- "path" is a file path relative to the workspace root (e.g. "index.js", "src/App.jsx").
- No markdown fences around the JSON. Output only the raw JSON object.
