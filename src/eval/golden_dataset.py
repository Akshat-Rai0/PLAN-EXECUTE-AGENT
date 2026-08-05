"""
The 20-goal golden dataset for the three-arm ablation study.

Categories (from docs/plan-and-execute-agent.html, section 07):
  (a) forced_replan       — a step fails and forces the replanner to revise
  (b) new_information     — a step surfaces info that changes the remaining plan
  (c) straightforward     — no replanning needed; baseline efficiency test
  (d) synthesis_required  — needs a tool not in the fixed registry; only
                             succeeds if dynamic tool synthesis works
  (e) browser_required    — requires browser automation with vision capabilities;
                             only succeeds if browser_use tool works correctly

Each goal records:
  - goal: the exact prompt text to run through an agent
  - category: one of the four above
  - expected_step_count: a human-set estimate, used only as a rough sanity
    signal in reports (LLM planners are non-deterministic in step count;
    this is NOT a hard pass/fail gate)
  - required_capability: "search" | "code_exec" | "synthesis" | "reasoning"
    | "shell" | "browser" — informs which arms a goal is even solvable on
  - success_criteria: plain-language description handed to the LLM judge
    alongside the goal and the final answer, so the judge knows what
    "correct" means for this specific goal (a generic "is this a good
    answer?" prompt is too weak to catch e.g. a wrong date or wrong
    formula silently slipping through)

DESIGN NOTE on specificity (2026-07-24 revision):
Several goals in the original draft were under-specified in a way that
actively hurts eval quality — not just "vague" stylistically, but vague in
ways that make the judge's job ill-defined:
  - Time-relative phrases like "most recent race" or "yesterday's match"
    are moving targets: the correct answer changes depending on *when* the
    eval is run, so a static success_criteria can't say what "correct"
    looks like without re-deriving it each run. Replaced with goals that
    still require a real search (so the (b) new_information mechanic is
    preserved — the agent doesn't know the answer in advance) but whose
    correctness is checkable against a fixed, named referent (e.g. "the
    2024 Formula 1 Constructors' Championship winner" — settled history,
    but not something to assume the base model recalls precisely, so the
    search step still matters).
  - "A major AI company" / "the top 3 programming languages" left the
    judge to accept almost any answer as plausible. Named a specific,
    concrete anchor company/subject so the second search step can be
    checked against what the first step actually returned, not against a
    fuzzy category.

BROWSER TEST NOTE (2026-08-05 revision):
Category (e) browser_required goals test the browser_use tool integration.
These goals specifically require rendered-page interaction and vision 
capabilities - they should FAIL if the agent falls back to web_search 
instead of using browser_use. The success criteria explicitly check that
browser automation was used, not just that the information was obtained
through other means.

STRESS TEST NOTE (2026-08-05 revision):
Category stress_* goals are designed to test system limits and robustness.
Each category has one stress test that pushes the boundaries of normal operation:
- Multiple consecutive failures (forced_replan)
- Long dependency chains (new_information) 
- Complex multi-step computations (straightforward)
- Tool synthesis and reuse (synthesis_required)
- Complex multi-step browser workflows (browser_required)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Category = Literal[
    "forced_replan",
    "new_information",
    "straightforward",
    "synthesis_required",
    "browser_required",
]

Capability = Literal["search", "code_exec", "synthesis", "reasoning", "shell", "browser"]


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
             "from the current workspace directory, then confirm it is "
             "gone by checking that a subsequent `ls` or file-existence "
             "check no longer lists it.",
        category="forced_replan",
        expected_step_count=3,
        required_capability="shell",
        success_criteria=(
            "The agent should attempt the delete, have it fail with a "
            "file-not-found error (not a permissions error or something "
            "else), and the final answer must explicitly state the file "
            "did not exist / did not need deleting. Score FAIL if the "
            "agent claims the delete succeeded, or if it issues more than "
            "2 additional retries of the identical delete command after "
            "the first failure."
        ),
    ),
    GoldenGoal(
        id="a2",
        goal="Write a Python script named read_csv_rows.py that opens a "
             "file called nonexistent_input.csv in the current directory "
             "using pandas.read_csv, and prints the number of rows via "
             "`len(df)`. Run the script and report the row count.",
        category="forced_replan",
        expected_step_count=3,
        required_capability="code_exec",
        success_criteria=(
            "Running the script must fail with a FileNotFoundError (or "
            "equivalent pandas error). The final answer must state that "
            "nonexistent_input.csv does not exist rather than reporting "
            "any numeric row count. Score FAIL if any specific number of "
            "rows is reported as the answer."
        ),
    ),
    GoldenGoal(
        id="a3",
        goal="In a fresh directory, scaffold a new React app using "
             "`npm create vite@latest my-counter-app -- --template react`, "
             "install dependencies, replace the contents of src/App.jsx "
             "with a component containing a single button that increments "
             "a displayed counter on click, and start the dev server with "
             "`npm run dev`. Report the URL the dev server is listening on.",
        category="forced_replan",
        expected_step_count=6,
        required_capability="shell",
        success_criteria=(
            "Scaffolding, `npm install`, and the App.jsx edit must all "
            "succeed. The final answer must either (a) report a specific "
            "localhost URL and port confirmed via process/port-listening "
            "check, or (b) if the dev server genuinely cannot be verified "
            "as running in this sandboxed environment, say so explicitly "
            "and give the command the user would run locally — rather "
            "than looping on repeated identical 'is it running yet' "
            "checks past 3 attempts."
        ),
        notes="Regression goal for the dev-server port-detection saga — "
              "see conversation history. Good canary for future regressions "
              "in this exact path.",
    ),
    GoldenGoal(
        id="a4",
        goal="Using Python's requests library, send a GET request to "
             "https://this-domain-should-not-resolve-xyz.invalid/rate and "
             "attempt to parse a USD-to-EUR exchange rate from the "
             "response. If that fails, find the current USD-to-EUR rate "
             "by another means and report it with its source.",
        category="forced_replan",
        expected_step_count=3,
        required_capability="code_exec",
        success_criteria=(
            "The initial request must fail with a DNS resolution or "
            "connection error (this is expected and by design — not a bug "
            "to work around). The final answer must either report a real "
            "USD/EUR rate obtained from a genuine alternative source with "
            "that source named, or explicitly state no reliable rate "
            "could be obtained. Score FAIL if a specific rate is reported "
            "without a real source, or if the invalid domain is claimed "
            "to have returned data."
        ),
    ),
    # ------------------------------------------------------------------
    # (b) new_information — a step surfaces info that changes remaining plan
    # ------------------------------------------------------------------
    GoldenGoal(
        id="b1",
        goal="Search for the winner of the latest Formula 1 race' "
             "then search specifically for that driver's "
             "final time margin over the runner-up.",
        category="new_information",
        expected_step_count=3,
        required_capability="search",
        success_criteria=(
            "The first step must identify the winner of the latest Formula 1 race. "
            "The second step must use that driver's name in a follow-up search for "
            "their winning margin over the runner-up, rather than repeating a "
            "generic race-results query. The final answer must report the specific "
            "time margin between the winner and the runner-up, consistent with "
            "official race results."
        ),
    ),
    GoldenGoal(
        id="b2",
        goal="Search for who is the current CEO of OpenAI as of today's "
             "date, then search specifically for the month and year they "
             "took that role to calculate their approximate tenure length.",
        category="new_information",
        expected_step_count=4,
        required_capability="search",
        success_criteria=(
            "The second search's query must be built around the specific "
            "name returned by the first search (e.g. 'Sam Altman start "
            "date OpenAI CEO'), not a generic restatement of the first "
            "query. Final answer must name a real, currently-accurate "
            "CEO and report a tenure length consistent with public "
            "record as of the search date."
        ),
    ),
    GoldenGoal(
        id="b3",
        goal="Search for the programming language ranked #1 on the "
             "current TIOBE Index, then search specifically for two "
             "concrete reasons cited for that language's popularity this "
             "year and summarize them.",
        category="new_information",
        expected_step_count=4,
        required_capability="search",
        success_criteria=(
            "The second search and final summary must be specifically "
            "about the language actually returned as #1 in the first "
            "step — score FAIL if the summary is generic boilerplate "
            "that would apply equally to any top-ranked language (e.g. "
            "'it has a large community and many libraries') without at "
            "least one concrete, language-specific fact from the search."
        ),
    ),
    GoldenGoal(
        id="b4",
        goal="Search for the result of the most recent NBA Finals series, "
             "identify the winning team, then search specifically for "
             "what the pre-series betting odds or expert predictions were "
             "for that matchup, and state whether the actual result "
             "matched those predictions.",
        category="new_information",
        expected_step_count=4,
        required_capability="search",
        success_criteria=(
            "Requires the agent to first identify a specific series and "
            "winning team, then run a second, narrower search specifically "
            "for pre-series predictions/odds for that exact matchup — "
            "score FAIL if the second search is a generic repeat of the "
            "first, or if the final answer doesn't explicitly compare "
            "predicted vs. actual outcome."
        ),
    ),
    # ------------------------------------------------------------------
    # (c) straightforward — no replanning needed, baseline efficiency test
    # ------------------------------------------------------------------
    GoldenGoal(
        id="c1",
        goal="Convert 98.6 degrees Fahrenheit to Celsius, showing the "
             "formula used.",
        category="straightforward",
        expected_step_count=3,
        required_capability="reasoning",
        success_criteria="Final answer must state 37.0°C (or 37°C) and "
                          "show the formula (F-32)*5/9.",
    ),
    GoldenGoal(
        id="c2",
        goal="Write a Python script named reverse.py containing a "
             "function reverse_string(s) that returns the input string "
             "reversed, plus a __main__ block that calls it on the "
             "literal string 'hello world' and prints the result. Run it "
             "and report the printed output.",
        category="straightforward",
        expected_step_count=3,
        required_capability="code_exec",
        success_criteria=(
            "reverse.py must be created and, when executed, print exactly "
            "'dlrow olleh' as the reversed form of 'hello world'."
        ),
    ),
    GoldenGoal(
        id="c3",
        goal="Compare REST and GraphQL APIs across these four specific "
             "dimensions: (1) over-fetching/under-fetching of data, (2) "
             "caching strategy, (3) API versioning approach, and (4) "
             "tooling/ecosystem maturity. Give at least one concrete "
             "example for each dimension.",
        category="straightforward",
        expected_step_count=5,
        required_capability="reasoning",
        success_criteria=(
            "All four named dimensions must be addressed for both REST "
            "and GraphQL, each with at least one concrete example (e.g. "
            "an actual query shape, cache header, or versioning scheme) "
            "rather than only abstract generalities."
        ),
    ),
    GoldenGoal(
        id="c4",
        goal="Write a Python script named greet.py that reads a single "
             "line of input in the format 'Name,Age' (e.g. 'Alice,30'), "
             "splits on the comma, and prints exactly: "
             "'Hello, Alice! You are 30 years old.' Run it with the "
             "sample input 'Alice,30' and report the output.",
        category="straightforward",
        expected_step_count=3,
        required_capability="code_exec",
        success_criteria=(
            "Script must be written and successfully executed with the "
            "input 'Alice,30', producing the exact output string "
            "'Hello, Alice! You are 30 years old.'"
        ),
    ),
    # ------------------------------------------------------------------
    # (d) synthesis_required — needs a tool not in the fixed registry
    # ------------------------------------------------------------------
    GoldenGoal(
        id="d1",
        goal="Generate a QR code encoding the exact text 'hello world' "
             "and save it as qrcode.png in the current directory, using "
             "whatever library is needed (e.g. the `qrcode` Python "
             "package) since no QR-generation tool exists in the fixed "
             "tool registry.",
        category="synthesis_required",
        expected_step_count=3,
        required_capability="synthesis",
        success_criteria=(
            "No fixed tool can do this — the agent must synthesize a tool "
            "(e.g. pip-install and call the `qrcode` library) and "
            "successfully produce a valid, non-empty qrcode.png file. "
            "Category (d) goals should FAIL on an arm without synthesis "
            "and SUCCEED on an arm with it — this is the cleanest signal "
            "in the whole ablation."
        ),
    ),
    GoldenGoal(
        id="d2",
        goal="Calculate the SHA-256 hash of the exact ASCII string "
             "'plan-execute-agent' (no trailing newline) and report it as "
             "a 64-character lowercase hexadecimal string.",
        category="synthesis_required",
        expected_step_count=2,
        required_capability="synthesis",
        success_criteria=(
            "The exact correct SHA-256 hex digest of 'plan-execute-agent' "
            "must be reported: "
            "b1a3f4e9d5f6bb9d0d6c7c8b56a2a9c26935f0c0a2f2a9a4b5cbf8f2e4d6a7b1 "
            "is a placeholder — the judge/harness should independently "
            "compute hashlib.sha256(b'plan-execute-agent').hexdigest() "
            "and do an exact string comparison rather than eyeballing "
            "plausibility."
        ),
        notes="Deterministic — implement as an exact-match check in the "
              "harness, not an LLM-judge call.",
    ),
    GoldenGoal(
        id="d3",
        goal="Convert the color hex code #FF5733 to its RGB equivalent, "
             "reporting each channel (R, G, B) as a decimal 0-255 value.",
        category="synthesis_required",
        expected_step_count=2,
        required_capability="synthesis",
        success_criteria=(
            "Correct, deterministic answer: R=255, G=87, B=51. Judge "
            "should check for exactly these three numbers, in that "
            "channel order."
        ),
        notes="Deterministic — good candidate for an exact-match check.",
    ),
    GoldenGoal(
        id="d4",
        goal="Generate a UUID version 4 value (e.g. using Python's "
             "uuid.uuid4()) and verify programmatically that it matches "
             "the standard UUID4 format before reporting it.",
        category="synthesis_required",
        expected_step_count=2,
        required_capability="synthesis",
        success_criteria=(
            "A syntactically valid UUID4 string (8-4-4-4-12 hex groups, "
            "the version nibble at position 13 equal to '4', and the "
            "variant nibble at position 17 in {8,9,a,b}) must be produced "
            "and reported, along with confirmation that the format check "
            "was actually run (not just asserted)."
        ),
    ),
    # ------------------------------------------------------------------
    # (e) browser_required — requires browser automation with vision
    # ------------------------------------------------------------------
    GoldenGoal(
        id="e1",
        goal="Navigate to https://www.google.com/travel/flights and "
             "search for flights from San Francisco (SFO) to New York (JFK) "
             "for next week, then report the top 3 airlines shown in the "
             "search results.",
        category="browser_required",
        expected_step_count=3,
        required_capability="browser",
        success_criteria=(
            "The agent must successfully navigate to the Google Travel "
            "flights page, fill in the origin (SFO) and destination (JFK) "
            "airports, set a date for next week, submit the search, and "
            "extract at least 3 airline names from the results. The final "
            "answer must list specific airlines (e.g. 'United, Delta, "
            "American') not generic confirmation that the search ran. "
            "Score FAIL if no specific airlines are reported or if the "
            "agent falls back to web_search instead of browser_use."
        ),
        notes="Tests form filling, date selection, and data extraction from "
              "rendered content. Requires vision to identify form fields "
              "and result elements."
    ),
    GoldenGoal(
        id="e2",
        goal="Go to https://example.com and extract the text content of "
             "the main heading (h1) and first paragraph (p) from the page.",
        category="browser_required",
        expected_step_count=2,
        required_capability="browser",
        success_criteria=(
            "The agent must navigate to example.com using browser_use, "
            "visually identify the h1 heading and first paragraph element, "
            "and extract their text content. The final answer must report "
            "the exact text of both elements. Score FAIL if the agent uses "
            "web_search instead of browser_use, or if it cannot identify "
            "the specific elements requested."
        ),
        notes="Basic browser navigation and element extraction test. "
              "Requires vision to identify page structure."
    ),
    GoldenGoal(
        id="e3",
        goal="Navigate to a weather website (e.g., weather.com) and find "
             "the current temperature for a specific city (e.g., 'London, "
             "UK') by interacting with the search box and reading the "
             "rendered results.",
        category="browser_required",
        expected_step_count=3,
        required_capability="browser",
        success_criteria=(
            "The agent must use browser_use to navigate to a weather site, "
            "locate the search box, enter the city name, submit the search, "
            "and extract the current temperature from the rendered results. "
            "The final answer must report a specific temperature value (e.g., "
            "'72°F' or '22°C'). Score FAIL if the agent uses web_search "
            "instead of browser_use, or if no specific temperature is "
            "reported."
        ),
        notes="Tests search box interaction and data extraction from "
              "dynamic content. Requires vision to identify search elements "
              "and read rendered temperature data."
    ),
    GoldenGoal(
        id="e4",
        goal="Visit https://github.com and navigate to the trending "
             "repositories section, then report the names of the top 3 "
             "trending repositories and their programming languages.",
        category="browser_required",
        expected_step_count=3,
        required_capability="browser",
        success_criteria=(
            "The agent must navigate to GitHub using browser_use, find "
            "the trending repositories section (may require navigation to "
            "a specific trending page), and extract the names and "
            "programming languages of at least 3 trending repositories. "
            "The final answer must list specific repository names and "
            "their languages (e.g., 'repository1 (Python), repository2 "
            "(JavaScript), repository3 (TypeScript)'). Score FAIL if the "
            "agent uses web_search or cannot extract specific repository "
            "information."
        ),
        notes="Tests navigation within a complex site and extraction of "
              "structured data from lists/cards. Requires vision to identify "
              "trending section and repository cards."
    ),
    GoldenGoal(
        id="e5",
        goal="Navigate to https://www.reddit.com/r/programming and "
             "extract the titles of the top 5 posts from the hot feed, "
             "along with their upvote counts.",
        category="browser_required",
        expected_step_count=3,
        required_capability="browser",
        success_criteria=(
            "The agent must use browser_use to navigate to the programming "
            "subreddit, identify the hot feed section, and extract the titles "
            "and upvote counts of at least 5 posts. The final answer must "
            "list specific post titles with their corresponding upvote counts. "
            "Score FAIL if the agent uses web_search instead of browser_use, "
            "or if it cannot extract the specific post information requested."
        ),
        notes="Tests social media feed navigation and structured data "
              "extraction. Requires vision to identify post cards and upvote "
              "elements in a dynamic feed layout."
    ),
    GoldenGoal(
        id="e6",
        goal="Go to https://www.amazon.com and search for 'Python programming "
             "books', then navigate to the first product result and extract "
             "the product title, price, and average customer rating.",
        category="browser_required",
        expected_step_count=4,
        required_capability="browser",
        success_criteria=(
            "The agent must use browser_use to navigate to Amazon, locate "
            "the search box, enter 'Python programming books', submit the search, "
            "click on the first product result, and extract the product title, "
            "price, and customer rating from the product page. The final answer "
            "must report specific values for all three data points. Score FAIL "
            "if the agent uses web_search instead of browser_use, or if it "
            "cannot extract the specific product information."
        ),
        notes="Complex e-commerce workflow: search, navigation, and product "
              "page data extraction. Requires vision to handle complex page "
              "layouts and dynamic content."
    ),
    GoldenGoal(
        id="e7",
        goal="Navigate to https://news.ycombinator.com and identify the "
             "current #1 story on the homepage, then report its title, "
             "points, and comment count.",
        category="browser_required",
        expected_step_count=2,
        required_capability="browser",
        success_criteria=(
            "The agent must use browser_use to navigate to Hacker News, "
            "visually identify the #1 ranked story, and extract its title, "
            "points, and comment count. The final answer must report all three "
            "specific values. Score FAIL if the agent uses web_search instead "
            "of browser_use, or if it cannot identify the #1 story correctly."
        ),
        notes="Tests ranking identification and structured data extraction from "
              "a minimal but content-dense page. Requires vision to distinguish "
              "between story ranks and extract metadata."
    ),
    # ------------------------------------------------------------------
    # STRESS TESTS — one per category to test system limits
    # ------------------------------------------------------------------
    # (a) STRESS TEST — forced_replan
    GoldenGoal(
        id="stress_a1",
        goal="Attempt to delete a file that doesn't exist, then attempt to "
             "delete another non-existent file with a different name, then "
             "attempt a third non-existent file deletion. The agent should "
             "handle each failure gracefully and report the correct status "
             "for all three attempts without getting stuck in a retry loop.",
        category="forced_replan",
        expected_step_count=5,
        required_capability="shell",
        success_criteria=(
            "The agent must attempt three separate file deletions for files "
            "that don't exist. Each attempt should fail with a file-not-found "
            "error. The agent should not retry any deletion more than 2 times "
            "after the initial failure. The final answer must explicitly state "
            "that none of the files existed. Score FAIL if the agent gets "
            "stuck in infinite retry loops or claims any deletion succeeded."
        ),
        notes="STRESS TEST: Tests the agent's ability to handle multiple "
              "consecutive failures without getting stuck in retry loops. "
              "Stresses the replanner's failure handling and retry logic."
    ),
    # (b) STRESS TEST — new_information
    GoldenGoal(
        id="stress_b1",
        goal="Search for the 2024 NBA Champions, then search for that team's "
             "starting lineup, then search for the head coach of that team, "
             "then search for the team's arena name, then search for the team's "
             "mascot. Each search must use information from the previous search.",
        category="new_information",
        expected_step_count=6,
        required_capability="search",
        success_criteria=(
            "The agent must perform 5 sequential searches where each search "
            "depends on information from the previous search. The chain must be: "
            "2024 NBA Champions → starting lineup → head coach → arena name → "
            "mascot. Each search must correctly incorporate the prior result. "
            "The final answer must report all 5 pieces of information correctly. "
            "Score FAIL if any search breaks the information chain or if the "
            "agent cannot maintain context across multiple steps."
        ),
        notes="STRESS TEST: Tests the agent's ability to maintain and use "
              "context across a long chain of dependent searches. Stresses "
              "context management and information flow between steps."
    ),
    # (c) STRESS TEST — straightforward
    GoldenGoal(
        id="stress_c1",
        goal="Search for the population of the 10 largest U.S. cities, then "
             "calculate the total population of all 10 cities combined, then "
             "calculate the average population, then identify which city has "
             "the highest population, then identify which has the lowest, then "
             "report the population difference between highest and lowest.",
        category="straightforward",
        expected_step_count=7,
        required_capability="search",
        success_criteria=(
            "The agent must search for populations of the 10 largest U.S. cities, "
            "then perform 5 sequential calculations: total, average, max, min, "
            "and difference between max and min. All calculations must be "
            "performed correctly based on the search results. The final answer "
            "must report all 6 results (individual populations, total, average, "
            "max city, min city, difference). Score FAIL if any calculation is "
            "incorrect or if the agent cannot handle the multi-step computation."
        ),
        notes="STRESS TEST: Tests the agent's ability to handle a complex "
              "multi-step computation task without replanning. Stresses "
              "reasoning and calculation capabilities on a single result set."
    ),
    # (d) STRESS TEST — synthesis_required
    GoldenGoal(
        id="stress_d1",
        goal="Create a synthesized tool that converts temperatures between "
             "Celsius, Fahrenheit, and Kelvin. Use this tool to convert a list "
             "of 10 different temperatures from Celsius to Fahrenheit, then use "
             "the same tool to convert the results to Kelvin, then verify the "
             "round-trip conversion by converting back to Celsius.",
        category="synthesis_required",
        expected_step_count=4,
        required_capability="synthesis",
        success_criteria=(
            "The agent must synthesize a temperature conversion tool that "
            "handles Celsius ↔ Fahrenheit ↔ Kelvin conversions. It must then "
            "use this tool to convert 10 temperatures through the full cycle: "
            "Celsius → Fahrenheit → Kelvin → Celsius. The round-trip conversions "
            "should return values close to the originals (allowing for rounding). "
            "The final answer must report the synthesized tool name, all "
            "conversion results, and verification that round-trip works. Score FAIL "
            "if the tool cannot be synthesized, if conversions are incorrect, or "
            "if the tool is not reused across steps."
        ),
        notes="STRESS TEST: Tests tool synthesis, reuse across multiple steps, "
              "and computational accuracy. Stresses the synthesis system's ability "
              "to create and reliably reuse complex tools."
    ),
    # (e) STRESS TEST — browser_required
    GoldenGoal(
        id="stress_e1",
        goal="Navigate to https://www.wikipedia.org, search for 'Artificial "
             "intelligence', click on the first result, scroll down to find the "
             "History section, extract the year when the term 'artificial "
             "intelligence' was coined, then navigate back to search, search "
             "for 'Machine learning', click the first result, and extract the "
             "definition from the opening paragraph.",
        category="browser_required",
        expected_step_count=6,
        required_capability="browser",
        success_criteria=(
            "The agent must perform a complex multi-step browser workflow: "
            "navigate to Wikipedia, search for 'Artificial intelligence', click "
            "first result, find History section, extract the coinage year, "
            "navigate back, search for 'Machine learning', click first result, "
            "and extract the definition. The final answer must report both the "
            "AI coinage year and the ML definition. Score FAIL if the agent uses "
            "web_search, cannot navigate correctly, cannot find specific page "
            "sections, or fails to extract the required information."
        ),
        notes="STRESS TEST: Tests complex multi-step browser navigation including "
              "search, clicking, scrolling, section identification, back navigation, "
              "and repeated search-extract cycles. Stresses browser session "
              "persistence and vision-based element identification across multiple "
              "page interactions."
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
    print(f"Blocked (missing capability): {len(blocked_goals())}")
    print(f"\nBrowser goals: {len([g for g in GOLDEN_DATASET if g.required_capability == 'browser'])}")
    print(f"Stress tests: {len([g for g in GOLDEN_DATASET if g.id.startswith('stress_')])}")