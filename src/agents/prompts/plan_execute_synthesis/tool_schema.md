You are declaring the interface contract for a new reusable tool needed to complete one step of a task. No standard fixed tool matches this requirement.

Overall goal: "{goal}"
Step that needs this capability: {step_task}

Prior steps and results:
{context_block}

Already-synthesized capabilities from earlier in this run (reuse one of these if applicable):
{existing_capabilities_block}

Declare a JSON object with exactly these keys:
- "capability_name": a short snake_case identifier (e.g. "convert_temperature_units", "calculate_mortgage_amortization")
- "description": one clear sentence describing what this tool does
- "input_description": plain-English description of the input shape (the tool receives a single JSON object as input)
- "output_description": plain-English description of the output shape (the tool must return a single JSON object)
- "example_input": a concrete example JSON object matching input_description (used to validate the generated function)

Contract Rules:
- Reuse Existing Names: If one of the already-synthesized capabilities listed above matches what this step needs, use that EXACT capability_name (character-for-character) and keep descriptions consistent.
- Reusable Design: Declare a genuinely reusable capability — general enough for similar future steps, not overfit to this specific step's wording.
- Simple Schemas: Keep input and output shapes flat and clean (standard string/number/bool/list values).
- Raw JSON Output: No markdown fences. Output ONLY the raw JSON object.

