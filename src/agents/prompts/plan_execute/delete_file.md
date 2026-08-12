You are determining what to delete for one step of a software task.

Today's date: {today}
Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Rules:
- Output a JSON object with exactly one key: "path"
- "path" is a file or directory path relative to the workspace root (e.g. "old_notes.txt", "src/legacy/").
- If the step means clearing everything in the workspace (e.g. "delete all files"), use "" as the path.
- No markdown fences around the JSON. Output only the raw JSON object.
