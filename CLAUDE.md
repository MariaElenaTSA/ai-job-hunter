# Career Copilot

## Project Goal

Career Copilot helps professionals understand their experience, discover relevant job opportunities, personalize resumes, and prepare for interviews using AI.

The project is also a learning project. The developer wants to understand every important architectural decision.

---

## How we work together

Before implementing any feature:

- Explain your understanding of the task.
- Identify only the files involved in the current milestone.
- Present a short implementation plan.
- Wait for approval if the change affects architecture.

---

## Scope and context efficiency

- Work only with files directly related to the current milestone.
- Start by reading the files explicitly identified in the task.
- Read additional files only when necessary to understand a direct dependency or avoid an incorrect change.
- Do not scan or summarize the entire repository unless explicitly requested.
- Keep analysis and implementation summaries concise.
- Do not explore or introduce unrelated refactors or architectural changes.
- During implementation, run only the tests directly related to the change.
- After the related tests pass, run the complete test suite once. Do not repeat it unless a failure requires another verification.
- Do not make live OpenAI calls unless explicitly requested.

---

## During implementation

Prefer:

- simple code
- readable code
- explicit variable names
- small functions
- minimal dependencies

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