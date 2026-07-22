"""
The 20-goal golden dataset for the three-arm ablation study.

Categories (from docs/plan-and-execute-agent.html, section 07):
  (a) forced_replan       — a step fails and forces the replanner to revise
  (b) new_information     — a step surfaces info that changes the remaining plan
  (c) straightforward     — no replanning needed; baseline efficiency test
  (d) synthesis_required  — needs a tool not in the fixed registry; only
                             succeeds if dynamic tool synthesis works
  (e) browser_only        — solvable only via real browser interaction
                             (NOT YET RUNNABLE — no browser tool exists yet,
                             see NOTE below)

Each goal records:
  - goal: the exact prompt text to run through an agent
  - category: one of the five above
  - expected_step_count: a human-set estimate, used only as a rough sanity
    signal in reports (LLM planners are non-deterministic in step count;
    this is NOT a hard pass/fail gate)
  - required_capability: "search" | "code_exec" | "synthesis" | "reasoning"
    | "browser" | "shell" — informs which arms a goal is even solvable on
  - success_criteria: plain-language description handed to the LLM judge
    alongside the goal and the final answer, so the judge knows what
    "correct" means for this specific goal (a generic "is this a good
    answer?" prompt is too weak to catch e.g. a wrong date or wrong
    formula silently slipping through)

NOTE on category (e), browser_only: per the codebase audit, no browser
automation tool exists yet (confirmed: no browser-related code anywhere in
the repo as of commit 018e1a6). These 4 goals are included in the dataset
now — per the original spec's structure — but are marked
`runnable_now=False`. The eval runner SKIPS them by default and reports
them separately as "blocked on missing capability" rather than silently
scoring them as failures, since a failure here would conflate "the agent
is bad" with "the agent is missing a tool it was never built to have yet."
Flip `runnable_now=True` once browser automation ships.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Category = Literal[
    "forced_replan",
    "new_information",
    "straightforward",
    "synthesis_required",
    "browser_only",
]

Capability = Literal["search", "code_exec", "synthesis", "reasoning", "browser", "shell"]


@dataclass(frozen=True)
class GoldenGoal:
    id: str
    goal: str
    category: Category
    expected_step_count: int
    required_capability: Capability
    success_criteria: str
    runnable_now: bool = True
    notes: str = ""


GOLDEN_DATASET: list[GoldenGoal] = [
    # ------------------------------------------------------------------
    # (a) forced_replan — a step fails, forcing a real replan
    # ------------------------------------------------------------------
    GoldenGoal(
        id="a1",
        goal="Delete the file named definitely_does_not_exist_xyz123.txt "
             "from the workspace, then confirm it is gone.",
        category="forced_replan",
        expected_step_count=3,
        required_capability="shell",
        success_criteria=(
            "The agent should attempt the delete, have it fail (file does "
            "not exist), and the final answer should clearly state the "
            "file was not found / did not need deleting — not silently "
            "claim success, and not loop indefinitely retrying the same "
            "delete."
        ),
    ),
    GoldenGoal(
        id="a2",
        goal="Write and run a Python script that reads a file called "
             "nonexistent_input.csv and prints its row count.",
        category="forced_replan",
        expected_step_count=3,
        required_capability="code_exec",
        success_criteria=(
            "The script execution should fail with a file-not-found style "
            "error, triggering a replan. The final answer should explain "
            "the file doesn't exist rather than fabricating a row count."
        ),
    ),
    GoldenGoal(
        id="a3",
        goal="Set up a new React app with Vite, create a simple counter "
             "component, and start the dev server.",
        category="forced_replan",
        expected_step_count=6,
        required_capability="shell",
        success_criteria=(
            "Scaffolding, install, and file-writing steps should all "
            "succeed. The dev server should eventually be confirmed "
            "running (or, if detection genuinely fails, the final answer "
            "should say so honestly with a URL to check manually) rather "
            "than the run exhausting the replan budget on repeated "
            "identical failures."
        ),
        notes="Regression goal for the dev-server port-detection saga — "
              "see conversation history. Good canary for future regressions "
              "in this exact path.",
    ),
    GoldenGoal(
        id="a4",
        goal="Fetch the current exchange rate from a URL that doesn't "
             "exist (https://this-domain-should-not-resolve-xyz.invalid/rate), "
             "then report the USD to EUR rate.",
        category="forced_replan",
        expected_step_count=3,
        required_capability="code_exec",
        success_criteria=(
            "The fetch should fail (DNS/connection error). The replanner "
            "should try an alternative approach (e.g. a real search) or "
            "the final answer should clearly state the specified source "
            "was unreachable, rather than fabricating a rate."
        ),
    ),
    # ------------------------------------------------------------------
    # (b) new_information — a step surfaces info that changes remaining plan
    # ------------------------------------------------------------------
    GoldenGoal(
        id="b1",
        goal="Who won the most recent Formula 1 race, and what was the "
             "winning margin?",
        category="new_information",
        expected_step_count=3,
        required_capability="search",
        success_criteria=(
            "The agent must identify the actual most recent race (not an "
            "outdated or hallucinated one) and report a winner name and a "
            "specific time-gap margin consistent with what the search "
            "results actually show."
        ),
    ),
    GoldenGoal(
        id="b2",
        goal="Find out who the current CEO of a major AI company is, then "
             "look up how long they've held that position.",
        category="new_information",
        expected_step_count=4,
        required_capability="search",
        success_criteria=(
            "The second search's query should be informed by the specific "
            "person/company identified in the first search, not a generic "
            "restatement. Final answer should name a real, current person "
            "and a plausible tenure length."
        ),
    ),
    GoldenGoal(
        id="b3",
        goal="Research the top 3 programming languages by GitHub stars, "
             "then summarize why the #1 language is popular.",
        category="new_information",
        expected_step_count=4,
        required_capability="search",
        success_criteria=(
            "The second half of the answer must specifically discuss the "
            "language actually identified as #1 in the first half — not a "
            "generic, could-apply-to-any-language explanation."
        ),
    ),
    GoldenGoal(
        id="b4",
        goal="What was the result of yesterday's most notable sports "
             "match, and did the outcome match pre-match predictions?",
        category="new_information",
        expected_step_count=4,
        required_capability="search",
        success_criteria=(
            "Requires the agent to first identify a specific match, then "
            "search specifically about that match's predictions/odds — "
            "generic re-searches without narrowing should be penalized."
        ),
    ),
    # ------------------------------------------------------------------
    # (c) straightforward — no replanning needed, baseline efficiency test
    # ------------------------------------------------------------------
    GoldenGoal(
        id="c1",
        goal="Convert 98.6 degrees Fahrenheit to Celsius.",
        category="straightforward",
        expected_step_count=3,
        required_capability="reasoning",
        success_criteria="Final answer must state 37.0°C (or 37°C).",
    ),
    GoldenGoal(
        id="c2",
        goal="Write a Python script that reverses a string and save it as "
             "reverse.py.",
        category="straightforward",
        expected_step_count=3,
        required_capability="code_exec",
        success_criteria=(
            "reverse.py must be created and, when executed with a sample "
            "input, correctly output the reversed string."
        ),
    ),
    GoldenGoal(
        id="c3",
        goal="Compare the pros and cons of REST vs GraphQL APIs.",
        category="straightforward",
        expected_step_count=5,
        required_capability="reasoning",
        success_criteria=(
            "A substantive, balanced comparison covering at least 3 "
            "distinct dimensions (e.g. performance, flexibility, tooling, "
            "caching) for both REST and GraphQL."
        ),
    ),
    GoldenGoal(
        id="c4",
        goal="Write a Python script that takes a name and age as "
             "comma-separated input and prints a formatted greeting.",
        category="straightforward",
        expected_step_count=3,
        required_capability="code_exec",
        success_criteria=(
            "Script must be written and successfully executed with a "
            "sample input, producing a correctly formatted greeting "
            "string containing both the name and age."
        ),
    ),
    # ------------------------------------------------------------------
    # (d) synthesis_required — needs a tool not in the fixed registry
    # ------------------------------------------------------------------
    GoldenGoal(
        id="d1",
        goal="Generate a QR code encoding the text 'hello world' and save "
             "it as qrcode.png.",
        category="synthesis_required",
        expected_step_count=3,
        required_capability="synthesis",
        success_criteria=(
            "No fixed tool can do this — the agent must synthesize a tool "
            "(e.g. using a QR-code library) and successfully produce "
            "qrcode.png. Category (d) goals should FAIL on an arm without "
            "synthesis and SUCCEED on an arm with it — this is the "
            "cleanest signal in the whole ablation."
        ),
    ),
    GoldenGoal(
        id="d2",
        goal="Calculate the SHA-256 hash of the string 'plan-execute-agent' "
             "and report it in hexadecimal.",
        category="synthesis_required",
        expected_step_count=2,
        required_capability="synthesis",
        success_criteria=(
            "The exact, correct SHA-256 hex digest must be reported. This "
            "is checkable deterministically: "
            "'2f1e7b9a' is NOT it — the judge should independently compute "
            "or be told the correct digest to compare against, not just "
            "eyeball plausibility."
        ),
        notes="Deterministic — good candidate for an exact-match check "
              "instead of relying solely on the LLM judge.",
    ),
    GoldenGoal(
        id="d3",
        goal="Convert the color hex code #FF5733 to its RGB equivalent.",
        category="synthesis_required",
        expected_step_count=2,
        required_capability="synthesis",
        success_criteria=(
            "Correct, deterministic answer: RGB(255, 87, 51). Judge should "
            "check for these three numbers specifically."
        ),
        notes="Deterministic — good candidate for an exact-match check.",
    ),
    GoldenGoal(
        id="d4",
        goal="Generate a UUID4 and validate that it matches the standard "
             "UUID4 format.",
        category="synthesis_required",
        expected_step_count=2,
        required_capability="synthesis",
        success_criteria=(
            "A syntactically valid UUID4 string (8-4-4-4-12 hex groups, "
            "version nibble '4', variant bits correct) must be produced "
            "and reported."
        ),
    ),
    # ------------------------------------------------------------------
    # (e) browser_only — NOT YET RUNNABLE, no browser tool exists
    # ------------------------------------------------------------------
    GoldenGoal(
        id="e1",
        goal="Search for a flight from NYC to London on a booking site and "
             "report the cheapest option's price.",
        category="browser_only",
        expected_step_count=5,
        required_capability="browser",
        success_criteria="Requires real browser interaction with a booking "
                          "flow — no API/search substitute exists.",
        runnable_now=False,
        notes="Blocked: no browser automation tool implemented yet.",
    ),
    GoldenGoal(
        id="e2",
        goal="Log into a demo dashboard site and report the values shown "
             "on the main summary widget.",
        category="browser_only",
        expected_step_count=4,
        required_capability="browser",
        success_criteria="Requires interacting with a login form and "
                          "reading rendered DOM content behind auth.",
        runnable_now=False,
        notes="Blocked: no browser automation tool implemented yet.",
    ),
    GoldenGoal(
        id="e3",
        goal="Fill out a public contact form on a test site with sample "
             "data and confirm the submission succeeded.",
        category="browser_only",
        expected_step_count=4,
        required_capability="browser",
        success_criteria="Requires filling and submitting an actual HTML "
                          "form via browser interaction.",
        runnable_now=False,
        notes="Blocked: no browser automation tool implemented yet.",
    ),
    GoldenGoal(
        id="e4",
        goal="Navigate to a product listing page, apply a price filter via "
             "the UI, and report the first result after filtering.",
        category="browser_only",
        expected_step_count=5,
        required_capability="browser",
        success_criteria="Requires interacting with client-side filter "
                          "UI controls, not just reading static HTML.",
        runnable_now=False,
        notes="Blocked: no browser automation tool implemented yet.",
    ),
]


def by_category(category: Category) -> list[GoldenGoal]:
    return [g for g in GOLDEN_DATASET if g.category == category]


def runnable_goals() -> list[GoldenGoal]:
    """Goals that can actually be attempted with tools that exist today."""
    return [g for g in GOLDEN_DATASET if g.runnable_now]


def blocked_goals() -> list[GoldenGoal]:
    """Goals present in the spec but not yet runnable (missing capability)."""
    return [g for g in GOLDEN_DATASET if not g.runnable_now]


if __name__ == "__main__":
    # Quick sanity print — not a test, just eyeballing the dataset shape.
    from collections import Counter

    cats = Counter(g.category for g in GOLDEN_DATASET)
    print(f"Total goals: {len(GOLDEN_DATASET)}")
    for cat, count in cats.items():
        print(f"  {cat}: {count}")
    print(f"Runnable now: {len(runnable_goals())}")
    print(f"Blocked (no browser tool): {len(blocked_goals())}")
