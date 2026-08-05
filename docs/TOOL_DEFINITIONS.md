# Enhanced Tool Definitions with Usage Guidelines

This document provides comprehensive tool definitions with clear "when to use" guidelines, examples, and detailed descriptions for all tools in the Plan-and-Execute Agent system.

## Table of Contents
- [LOW-RISK TOOLS](#low-risk-tools)
- [HIGH-RISK TOOLS](#high-risk-tools)
- [Specialized Tools](#specialized-tools)

---

## LOW-RISK TOOLS

### tavily_search
**Risk Level:** LOW (read-only information gathering)

**When to Use:**
- When you need current information from the internet (news, facts, data)
- When the answer isn't known or requires verification from external sources
- When you need specific details about people, events, products, or topics
- As the FIRST choice for information gathering before considering other tools

**When NOT to Use:**
- For pure reasoning or analysis of existing information (use reason/none)
- For calculations or data processing (use code_executor)
- When you already have the needed information in context
- For rendered page interaction or form filling (use browser_use)

**Examples:**
- "Search for the current CEO of Microsoft"
- "Find the population of Tokyo according to 2024 census data"
- "Look up the latest Python version release date"
- "Search for reviews of the iPhone 15 Pro camera quality"

**Implementation:** `src/tools/registry.py::tavily_search`

---

### today_date
**Risk Level:** LOW (read-only system information)

**When to Use:**
- When the goal explicitly asks for today's date or current date
- When you need to anchor time-sensitive queries to the current date
- When processing recency-sensitive information that needs a date reference
- Automatically injected for goals containing recency language ("latest", "recent", "current")

**When NOT to Use:**
- When you need date calculations or manipulation (use code_executor)
- When you need historical dates or date ranges (use search)
- When the task doesn't involve time-sensitive information

**Examples:**
- "What's today's date?" → Direct call returns "2026-08-05"
- "Who won the World Cup this year?" → Date anchor prepended before search
- "What are the latest stock prices?" → Date anchor ensures current data
- "Find recent Python job postings" → Date anchor for recency filtering

**Implementation:** `src/tools/registry.py::today_date`

---

### reason/none
**Risk Level:** LOW (pure LLM reasoning)

**When to Use:**
- For analysis, planning, or synthesis of existing information
- When you have all necessary context and just need to process it
- For decision-making based on prior step results
- For summarizing or combining information from multiple sources
- When the task requires logical reasoning but no external data
- For planning itineraries, budgets, or strategies based on gathered info

**When NOT to Use:**
- When you need to gather new information (use tavily_search instead)
- For calculations or data processing (use code_executor instead)
- When you need to interact with files or systems (use appropriate tools)
- When the task requires external APIs or services
- For tasks that need visual understanding (use browser_use)

**Examples:**
- "Analyze the search results and identify the best option"
- "Plan a 3-day itinerary based on the gathered information"
- "Create a budget from the price information collected"
- "Determine the winner from the tournament results"
- "Summarize the key findings from the research"
- "Compare the options and recommend the best choice"

**Capabilities:**
- Grounded in current date (recency-aware reasoning)
- Access to all prior step results for context
- Can synthesize information from multiple sources
- Makes real LLM calls (not silent no-ops)

**Implementation:** `src/agents/plan_execute/nodes.py::reason_node`

---

### setup_workspace
**Risk Level:** LOW (directory creation only)

**When to Use:**
- As the FIRST step in any app/coding task
- When creating a new project structure
- Before scaffolding, file creation, or development work
- When the task requires a dedicated working directory
- For organizing project files and keeping workspace clean

**When NOT to Use:**
- When a workspace already exists (check state first)
- For simple file operations that don't need a project structure
- When working with temporary files (use temp directories instead)
- For operations that don't require file system organization

**Examples:**
- "Create a new React project workspace"
- "Set up a Python project directory structure"
- "Initialize a workspace for the web application"
- "Create a project folder for the new API"
- "Set up a directory for the data processing pipeline"

**Capabilities:**
- Creates timestamped workspace directories
- Manages workspace lifecycle across steps
- Prevents workspace conflicts between runs
- Provides clean slate for each new project
- Integrates with all file and shell operations

**Implementation:** `src/agents/plan_execute/nodes.py::setup_workspace_node`

---

## HIGH-RISK TOOLS

### shell_command_tool
**Risk Level:** HIGH (can execute arbitrary commands)

**When to Use:**
- For development commands: npm install, pip install, git operations
- For project scaffolding: npx create-vite, cargo init, go mod init
- For build processes: npm run build, make, cargo build
- For package management: npm, pip, cargo, yarn, composer
- For version control: git clone, git checkout, git branch
- For directory operations: mkdir, ls (when not using dedicated file tools)

**When NOT to Use:**
- For file deletion (use delete_file_tool - rm is blocked for safety)
- For writing/reading files (use write_file_tool instead)
- For starting dev servers (use start_dev_server_tool instead)
- For arbitrary system commands or administrative tasks (safety restriction)
- For commands requiring user input (non-interactive execution only)

**Examples:**
- "npm install" → Install dependencies from package.json
- "npx create-vite@latest my-app -- --template react" → Scaffold React app
- "git clone https://github.com/user/repo.git" → Clone repository
- "pip install -r requirements.txt" → Install Python dependencies
- "ls -la" → List directory contents (when needed for exploration)
- "mkdir -p src/components" → Create directory structure

**Safety Notes:**
- 'rm' command is intentionally blocked - use delete_file_tool instead
- Commands run in sandboxed environment with timeout and memory limits
- Network access is restricted to allowlisted domains only
- Commands requiring user input will fail (non-interactive execution)

**Implementation:** `src/tools/registry.py::shell_command_tool`

---

### write_file_tool
**Risk Level:** HIGH (can write arbitrary files)

**When to Use:**
- Creating or editing source code files (JS, Python, HTML, CSS, etc.)
- Writing configuration files (package.json, tsconfig.json, .env files)
- Creating documentation files (README.md, docs, comments)
- Writing test files or specification files
- Creating data files (JSON, CSV, XML, etc.)
- After project scaffolding when implementing features

**When NOT to Use:**
- For file deletion (use delete_file_tool instead)
- For reading file contents (no dedicated read tool - use code_executor if needed)
- For appending to existing files (rewrite entire content instead)
- For binary files (text-based content only)

**Examples:**
- Write source code: "src/App.jsx" with React component code
- Configuration: "package.json" with project dependencies
- Documentation: "README.md" with project description
- Styles: "src/styles.css" with CSS rules
- Config: ".env.example" with environment variable templates
- Tests: "tests/app.test.js" with test cases

**Workflow Notes:**
- Automatically creates parent directories if they don't exist
- Overwrites existing files entirely (no append mode)
- Content should be complete file content, not partial updates
- Use after setup_workspace tool for project structure
- Typically followed by shell_command_tool for package installation

**Implementation:** `src/tools/registry.py::write_file_tool`

---

### delete_file_tool
**Risk Level:** HIGH (destructive operation)

**When to Use:**
- Cleaning up generated files or temporary artifacts
- Removing outdated configuration files
- Deleting specific source files during refactoring
- Clearing workspace contents for fresh start
- Removing build artifacts (node_modules, dist, build directories)
- ANY deletion task - never use shell 'rm' command

**When NOT to Use:**
- For reading file contents (use code_executor if needed)
- For moving/renaming files (delete and recreate instead)
- For operations outside the workspace (workspace-scoped only)
- When uncertain about file contents (destructive operation)

**Examples:**
- Delete specific file: "old_config.json" → Removes single file
- Delete directory: "node_modules/" → Removes entire directory tree
- Clear workspace: "" or "." → Deletes all workspace contents
- Remove build artifacts: "dist/" → Deletes build output directory
- Clean up: "*.tmp" → Deletes files matching pattern (if supported)
- Remove cache: ".cache/" → Deletes cache directory

**Safety Notes:**
- This is the ONLY safe way to delete files in the agent
- Shell 'rm' command is intentionally blocked for security
- Operation is irreversible - use with caution
- Workspace-scoped only - cannot delete files outside workspace
- Empty string "" clears entire workspace contents

**Implementation:** `src/tools/registry.py::delete_file_tool`

---

### code_executor
**Risk Level:** HIGH (can execute arbitrary Python code)

**When to Use:**
- For one-off calculations, data processing, or computational tasks
- When you need to manipulate or analyze data from prior steps
- For mathematical computations, statistical analysis, or data transformations
- When standard library operations suffice (no external dependencies needed)
- For generating test data, samples, or synthetic content
- When the task is a single-use calculation (not needing reusability)

**When NOT to Use:**
- For reusable functionality across multiple steps (use synthesize_tool instead)
- When the same logic needs to be applied to different inputs repeatedly
- For file operations (use write_file_tool, delete_file_tool instead)
- For network operations (use shell_command_tool or search instead)
- When the task requires persistent tools or complex dependencies

**Examples:**
- "Calculate the compound interest for a loan over 5 years"
- "Convert the temperature data from Celsius to Fahrenheit"
- "Generate a list of 100 random numbers and calculate statistics"
- "Parse the CSV data and filter rows where age > 25"
- "Calculate the SHA-256 hash of a given string"
- "Perform linear regression on the dataset and report the R-squared value"

**Capabilities:**
- Full Python standard library access (math, json, re, datetime, etc.)
- Automatic error detection and retry (up to 2 retries for fixable errors)
- Sandbox execution with timeout (default: 15 seconds) and memory limits
- Access to workspace files for reading/writing
- Command-line argument support for dynamic input values
- Comprehensive error reporting with stderr capture

**Constraints:**
- No external package imports (standard library only)
- No network access (security restriction)
- No interactive input() calls (non-interactive execution)
- Timeout enforced (prevents infinite loops)
- Memory limits prevent resource exhaustion
- Results must be printed to stdout for capture

**Implementation:** `src/agents/plan_execute/nodes.py::code_executor_node`

---

### synthesize_tool
**Risk Level:** HIGH (generates and executes new code at runtime)

**When to Use (triggered automatically by graph routing):**
- When the planner requests a capability not in the fixed tool registry
- When a step's tool_hint doesn't match any standard tool
- When reusable functionality is needed across multiple steps
- For specialized calculations, transformations, or integrations
- When the same logic needs to be applied to different inputs repeatedly

**When NOT to Use:**
- For one-off calculations (use code_executor instead)
- When standard tools suffice (search, shell, file operations)
- For simple operations that don't need reusability
- When the task can be accomplished with existing fixed tools

**Examples of synthesized capabilities:**
- "convert_temperature_units" - Reusable temperature conversion
- "fetch_exchange_rate" - Currency rate fetching with caching
- "calculate_business_metrics" - Domain-specific calculations
- "parse_custom_data_format" - Proprietary data format parsing
- "apply_pricing_logic" - Business rule implementation

**Workflow:**
1. Check if tool already exists in registry (reuse if found)
2. If new tool needed, declare schema via LLM (input/output contract)
3. Generate Python code implementation via LLM
4. Validate code in sandbox (test with example input)
5. Register successful tool for reuse across steps
6. Execute tool with actual step input
7. Return result or mark step FAILED if validation fails

**Capabilities:**
- Dynamic tool creation based on step requirements
- Tool registry for reuse across steps and runs
- Schema-first approach (declare before implementation)
- Sandbox validation for security
- Automatic retry on validation failures
- Integration with existing tool ecosystem

**Security:**
- Code runs in sandboxed environment
- No file I/O or network access (pure computation)
- Standard library only (no external dependencies)
- Validation before registration
- Memory and timeout limits
- HIGH-risk classification (requires approval)

**Implementation:** `src/agents/plan_execute/nodes.py::synthesize_tool_node`

---

### start_server_tool
**Risk Level:** HIGH (can start network services)

**When to Use:**
- Starting web development servers (React, Vue, Angular dev servers)
- Running backend API servers (Flask, Django, Express dev servers)
- Starting static file servers (python http.server, live-server)
- Launching database servers for local development
- Running development environments that need HTTP access
- As the FINAL step in app-building workflows

**When NOT to Use:**
- For production deployments (dev servers only)
- For one-off command execution (use shell_command_tool instead)
- For servers that don't need HTTP access (use shell_command_tool)
- For long-running background processes (dev servers only)
- When server startup isn't the goal of the task

**Examples:**
- React dev server: "npm run dev" on port 5173
- Python HTTP server: "python3 -m http.server 8000" on port 8000
- Flask dev server: "flask run --port 5000" on port 5000
- Vite dev server: "npm run dev" on port 3000
- Express dev server: "node server.js" on port 8080
- Django dev server: "python manage.py runserver" on port 8000

**Workflow Notes:**
- Typically used as the LAST step after scaffolding and file creation
- Server runs in background with timeout and port detection
- Returns localhost URL for manual testing or verification
- Process is killed after timeout or when agent completes
- Should follow shell_command_tool for dependency installation

**Technical Details:**
- Non-blocking execution with port-open detection
- Timeout-based process management (prevents hanging)
- Stderr capture for error diagnostics
- Process cleanup on completion or failure
- Network access restrictions still apply

**Implementation:** `src/tools/registry.py::start_dev_server_tool`

---

### browser_use
**Risk Level:** HIGH (can interact with third-party websites)

**When to Use:**
- When you need to interact with rendered websites (not just scrape HTML)
- For form filling and submission on web pages
- When visual page understanding is required (identifying elements by sight)
- For multi-step interactions requiring page state persistence
- When JavaScript-rendered content needs to be accessed
- For tasks that require human-like browsing behavior

**When NOT to Use:**
- For simple information retrieval (use tavily_search instead)
- When static HTML scraping would suffice (use search/code_executor)
- For API calls or data fetching (use code_executor with requests library)
- When the task doesn't require visual element identification
- For high-volume automated scraping (browser is resource-intensive)

**Examples:**
- "Navigate to Google Travel flights and search for SFO to JFK flights"
- "Go to example.com and extract the main heading text"
- "Fill out a contact form with name, email, and message"
- "Navigate to weather.com and find current temperature for London"
- "Go to GitHub and find trending repositories with their languages"
- "Login to a dashboard and navigate to the settings page"

**Capabilities:**
- Vision-enabled page understanding (identifies elements visually)
- Form filling and submission
- Multi-step navigation with session persistence
- Dynamic content interaction (JavaScript-heavy sites)
- Element identification using visual cues and DOM structure
- Screenshot generation for debugging

**Technical Details:**
- Uses OpenRouter's Gemma model with structured outputs
- Vision capabilities enabled for rendered page analysis
- Session persistence across steps within a single task
- Configurable step limits and failure tolerance
- HIGH-risk classification (requires approval before execution)

**Implementation:** `src/tools/browser_use/runner.py::run_browser_task`

---

## Specialized Tools

### Dynamic Tool Synthesis (declare_schema, generate_function_code)

**When to Use:**
- When creating reusable tools that don't exist in the fixed registry
- When the same computation logic needs to be applied across multiple steps
- For specialized capabilities like unit conversions, data transformations, API integrations
- When building domain-specific functionality that will be reused

**When NOT to Use:**
- For one-off calculations (use code_executor instead)
- When standard tools suffice for the task
- For simple operations that don't benefit from reusability

**Schema Declaration Phase:**
- Declares input/output contract before implementation
- Checks existing registry for reusable capabilities
- Ensures consistent interface design
- Prevents duplicate tool creation

**Code Generation Phase:**
- Generates Python implementation against declared schema
- Enforces security constraints (no file I/O, no network)
- Standard library only for portability
- Must output JSON for result capture

**Implementation:** `src/synthesis/codegen.py`

---

## Tool Selection Decision Tree

```
Task Analysis
│
├─ Need current information?
│  └─ YES → tavily_search (web search)
│  └─ NO → Continue
│
├─ Need to analyze/plan with existing info?
│  └─ YES → reason/none (pure reasoning)
│  └─ NO → Continue
│
├─ Need calculation/computation?
│  ├─ One-time use? → code_executor
│  └─ Reusable across steps? → synthesize_tool
│
├─ Need file operations?
│  ├─ Write/create file → write_file_tool
│  ├─ Delete file → delete_file_tool
│  └─ Need project structure? → setup_workspace
│
├─ Need development commands?
│  ├─ Package install/build → shell_command_tool
│  ├─ Start dev server → start_server_tool
│  └─ Version control → shell_command_tool
│
├─ Need rendered page interaction?
│  └─ YES → browser_use (HIGH-risk, requires approval)
│
└─ Need specialized capability?
   └─ synthesize_tool (dynamic tool creation)
```

---

## Risk Classification Summary

### LOW-RISK (No approval required)
- tavily_search (read-only web search)
- today_date (system date read)
- reason/none (pure LLM reasoning)
- setup_workspace (directory creation)

### HIGH-RISK (Requires approval)
- shell_command_tool (arbitrary command execution)
- write_file_tool (arbitrary file writing)
- delete_file_tool (destructive file operations)
- code_executor (arbitrary Python code execution)
- synthesize_tool (dynamic code generation and execution)
- start_server_tool (network service startup)
- browser_use (third-party website interaction)

---

## Best Practices

1. **Start with LOW-RISK tools** - Always prefer read-only operations first
2. **Use approval gating** - HIGH-RISK tools require human confirmation
3. **Consider reusability** - Use synthesize_tool for logic that will be reused
4. **Prefer code_executor for one-offs** - Single calculations should use code_executor
5. **Never use shell rm** - Always use delete_file for any deletion
6. **Browser as last resort** - Only use browser_use when web_search cannot accomplish the task
7. **Follow tool ordering** - Use setup_workspace → shell_command → write_file → start_server sequence for app development
8. **Leverage context** - Tools can access prior step results for better performance
9. **Respect constraints** - Each tool has specific security and capability constraints
10. **Handle failures gracefully** - Tools return detailed error messages for debugging

---

## Performance Optimization Tips

1. **Use search_depth="basic"** for simple queries, "advanced" only when needed
2. **Enable recency_sensitive** only for time-sensitive queries
3. **Reuse synthesized tools** across steps to avoid regeneration
4. **Prefer specific searches** over broad queries to reduce irrelevant results
5. **Use reason node** when all context is already available
6. **Configure appropriate timeouts** based on task complexity
7. **Limit result sizes** to reduce token usage
8. **Use standard library only** in code_executor for faster execution
9. **Batch operations** when possible to reduce tool calls
10. **Cache results** in tool registry for repeated operations

---

This documentation provides comprehensive guidance for tool selection and usage within the Plan-and-Execute Agent system. Refer to individual tool implementations for technical details and constraints.