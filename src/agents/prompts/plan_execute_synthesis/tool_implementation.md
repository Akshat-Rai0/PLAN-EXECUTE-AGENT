Write a single Python function implementing this tool:

Capability: {schema.capability_name}
Description: {schema.description}
Input shape: {schema.input_description}
Output shape: {schema.output_description}

Rules:
- Define exactly one function that takes a single dict argument and returns a single dict.
- At the bottom of the script, read the input as JSON from sys.argv[1] (a single command-line
  argument containing the JSON-encoded input object), call your function with the parsed dict,
  and print the result as a single JSON object using print(json.dumps(result)) — this must be
  the LAST line of output. Example bottom-of-script pattern:
      import sys, json
      input_data = json.loads(sys.argv[1])
      result = your_function_name(input_data)
      print(json.dumps(result))
- Pure computation only: no input(), no file I/O, no network calls, no external packages — standard
  library only (json, math, datetime, re, etc. are fine).
- Keep it simple and correct for the declared shape.
- Do not include markdown code fences — output only the raw Python code.{retry_note}
