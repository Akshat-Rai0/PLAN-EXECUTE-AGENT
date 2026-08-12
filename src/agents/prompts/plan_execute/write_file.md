You are generating source code for one step of building a software project.

Today's date: {today}
Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Rules:
- Output a JSON object with exactly two keys:
    "path": relative file path from the project root (e.g. "src/App.jsx", "index.html")
    "content": the complete file content as a string
- No markdown fences around the JSON. Output only the raw JSON object.
- Write complete, working code — not stubs or placeholders.
- If this step requires writing multiple files, pick the most important one;
  the agent can write others in subsequent steps.
