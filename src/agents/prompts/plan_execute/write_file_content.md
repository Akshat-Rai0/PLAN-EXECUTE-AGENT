You are generating source code for one step of building a software project.

Today's date: {today}
Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}
File to write: {rel_path}

Prior steps and results:
{context_block}

Rules:
- Output a JSON object with exactly one key: "content"
- "content" is the complete file content as a string
- No markdown fences around the JSON. Output only the raw JSON object.
- Write complete, working code — not stubs or placeholders.
