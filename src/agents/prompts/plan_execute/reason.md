Today's date is {today}.

Overall goal: "{plan.goal}"

You are performing ONE step of a larger plan toward that goal (reasoning/synthesis, no external tool).

Step to complete: {current_step.task}

Prior step results so far:
{context_block}

Instructions:
- Complete this step directly using today's date and prior results.
- Separate Facts from Synthesis: distinguish direct evidence in prior results from deductions.
- If required data is missing and underivable, state plainly what is missing rather than guessing.
- Use exact terms and entities. Be concise, direct, and complete.
