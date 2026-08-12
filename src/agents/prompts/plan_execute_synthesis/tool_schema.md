You are declaring the contract for a new reusable tool needed to complete one step of a task. No FIXED tool (search, file I/O, shell, etc.) matches this need.

Overall goal: "{goal}"
Step that needs this new capability: {step_task}

Prior steps and results:
{context_block}

Already-synthesized capabilities from earlier in this run (reuse one of these if it fits):
{existing_capabilities_block}

Declare a JSON object with exactly these keys:
- "capability_name": a short snake_case identifier, e.g. "convert_temperature_units" or "fetch_exchange_rate"
- "description": one sentence describing what this tool does
- "input_description": plain-English description of the input shape (this tool will be called with a single JSON object as input)
- "output_description": plain-English description of the output shape (this tool must return a single JSON object)
- "example_input": a concrete example input object matching input_description — this will be used to test the generated function

Rules:
- IMPORTANT: If one of the already-synthesized capabilities listed above already does what this step needs, set "capability_name" to that EXACT existing name (character-for-character), and keep "description"/"input_description"/"output_description" consistent with what that existing tool already does — do not invent a new, differently-worded name for the same underlying capability just because this step's wording differs.
- Only declare a genuinely NEW capability_name if none of the existing ones cover this step's need.
- The capability should be genuinely reusable — general enough that a similarly-phrased future step could use it too, not hyper-specific to this exact step's wording.
- Keep the input/output shapes simple: flat JSON objects with string/number/bool/list values, no nested custom types.
- No markdown fences. Output only the raw JSON object.
