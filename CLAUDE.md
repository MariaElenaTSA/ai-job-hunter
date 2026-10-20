When making roadmap, backlog, Jira, sprint, or product decisions, follow AI_PRODUCT_MANAGER.md before proposing changes.

# Career Copilot

## Project Goal

Career Copilot helps professionals understand their experience, discover relevant job opportunities, personalize resumes, and prepare for interviews using AI.

The project is also a learning project. The developer wants to understand every important architectural decision.

---

## How we work together

Before implementing any feature:

- Explain your understanding of the task.
- Challenge assumptions instead of accepting them automatically; point out when a simpler approach exists.
- Identify only the files involved in the current milestone.
- Present a short implementation plan.
- Wait for approval if the change affects architecture.

---

## Scope and context efficiency

- Work only with files directly related to the current milestone.
- Start by reading the files explicitly identified in the task.
- Read additional files only when necessary to understand a direct dependency or avoid an incorrect change.
- Avoid re-reading a file already inspected in the current session if its relevant content is still available.
- Do not scan or summarize the entire repository unless explicitly requested.
- Keep analysis and implementation summaries concise.
- Before writing or modifying code, check whether the change can be achieved by reusing existing code, tests, configuration, or components. Prefer extending what already exists over creating new files, dependencies, or abstractions — every new one should have a clear justification.
- Do not introduce unrelated refactors, architectural changes, or features outside the current milestone unless they are necessary for validation or risk reduction. Flag other useful-but-postponable work instead of doing it now.
- When editing, modify only the files necessary and prefer a targeted edit over rewriting an entire file.
- During implementation, run only the tests directly related to the change.
- After the related tests pass, run the complete test suite once. Do not repeat it unless a failure requires another verification.
- Do not make live OpenAI calls unless explicitly requested.

---

## Manual work vs. automation

- If a task takes a human about 1-2 minutes, needs little engineering reasoning, and is unlikely to repeat (moving a file, editing an env var, a simple git command), recommend doing it manually instead of spending effort automating it.
- If that same manual step is likely to repeat, become error-prone, or easy to forget, propose the smallest automation or config change that removes the repetition — no bigger than the repetition justifies.

---

## During implementation

Prefer:

- simple code
- readable code
- explicit variable names
- small functions
- minimal dependencies
- the smallest working solution over a more elaborate abstraction, when both safely achieve the goal
- simple, reversible changes over premature scalability or architecture for hypothetical future needs

---

## After implementation

Always provide:

- files modified
- summary of changes
- explanation of the diff
- how to test
- possible edge cases

---

## Git

Never commit automatically.

Suggest a commit message instead.

---

## Learning mode

Whenever introducing a new concept:

Explain:

- why it exists
- why we use it
- alternatives
- tradeoffs

Keep explanations concise.

---

## Coding style

Prefer:

- FastAPI best practices
- type hints
- clear comments only when necessary
- maintainability over cleverness