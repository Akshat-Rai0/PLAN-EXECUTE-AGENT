Today's date is {today}.

Overall goal: "{plan.goal}"

You are performing ONE step of a larger plan toward that goal. This step requires reasoning/synthesis, not an external tool call.

Step to complete: {current_step.task}

Prior step results so far:
{context_block}

Instructions:
- Complete this step directly and concretely, using today's date and the prior results above where relevant.
- If this step depends on information not present in the prior results and not derivable from today's date, say plainly what's missing rather than guessing.
- Do not restate the whole goal — just produce the output this specific step calls for.
- Be concise but complete.
