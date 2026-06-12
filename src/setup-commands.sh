#!/usr/bin/env bash
# Run this once from your project root. It creates learning-oriented Claude Code
# slash commands in .claude/commands/. Most are read-only by design: the AI can
# analyze and advise, but cannot write your core code for you.
#
#   bash setup-commands.sh
#
# Then restart Claude Code (or type /) and the commands appear in autocomplete.

set -euo pipefail
mkdir -p .claude/commands

cat > .claude/commands/hint.md <<'EOF'
---
description: Get one conceptual nudge when stuck — not the solution
argument-hint: [what you're stuck on]
allowed-tools: Read, Grep, Glob
---
I'm stuck on the following: $ARGUMENTS

You are helping me learn, not solving it for me. Do NOT write the solution code.
Give me exactly:
1. One short observation about where the problem likely is.
2. One guiding question that points me toward the answer myself.
If a concept would help, name it and tell me where to read about it.
Then stop — do not continue until I ask.
EOF

cat > .claude/commands/critique.md <<'EOF'
---
description: Review code I wrote — find issues and explain why, without rewriting it
argument-hint: [file or path]
allowed-tools: Read, Grep, Glob
---
Review the code in: $ARGUMENTS

I wrote this myself and want to improve it. Do NOT rewrite or edit the file.
Give prioritized feedback covering:
- Correctness, bugs, and edge cases I may have missed
- Design and readability
- Idiomatic Python and performance notes
For each point, explain the *reasoning* so I learn the underlying principle. Where
helpful, point to the smallest possible illustrative snippet (a line or two) — never
a full rewrite. End with the single most important thing to fix first.
EOF

cat > .claude/commands/review.md <<'EOF'
---
description: PR-style review of my staged changes before I commit
allowed-tools: Read, Grep, Glob, Bash(git diff:*), Bash(git status:*)
---
## Staged changes
!`git diff --cached`

Review the staged changes above as if reviewing a pull request. Do not edit anything.
Cover correctness, edge cases, security, clarity, and whether the change matches the
conventions in CLAUDE.md. Give prioritized, specific feedback. If it's ready, say so
and suggest a concise conventional-commit message.
EOF

cat > .claude/commands/explain.md <<'EOF'
---
description: Explain a concept or piece of code in the context of this project
argument-hint: [concept or file]
allowed-tools: Read, Grep, Glob
---
Explain: $ARGUMENTS

Assume I'm a final-year CS student who wants to truly understand this, not just use it.
Be concise but build intuition: what it is, why it matters here, and one small concrete
example grounded in this project. Name any important tradeoffs or common pitfalls.
Do not write project code for me.
EOF

cat > .claude/commands/refactor.md <<'EOF'
---
description: Suggest refactorings with rationale — I apply them myself
argument-hint: [file or path]
allowed-tools: Read, Grep, Glob
---
Suggest refactorings for: $ARGUMENTS

Do NOT edit the file. List concrete suggestions, each with: what to change, why it's
better, and a minimal before/after snippet (a few lines at most). Order by impact.
Leave the actual editing to me.
EOF

cat > .claude/commands/rubber-duck.md <<'EOF'
---
description: Socratic debugging — help me find the bug myself
argument-hint: [the bug or behavior]
allowed-tools: Read, Grep, Glob
---
I'm debugging: $ARGUMENTS

Be my rubber duck. Do NOT tell me the fix. Ask me one focused question at a time about
my assumptions, the data, and what I've already checked, to help me locate the problem
myself. Wait for my answer before asking the next question.
EOF

cat > .claude/commands/defend.md <<'EOF'
---
description: Role-play a thesis examiner grilling me on my own code
argument-hint: [file or topic]
allowed-tools: Read, Grep, Glob
---
Act as a strict but fair thesis examiner. Open and read: $ARGUMENTS

Quiz me the way a defense committee would, one pointed question at a time: what this
code does, why I designed it this way, what the alternatives were, what happens under
edge cases or failure, and how it connects to the project's goals. Wait for my answer
each time, then judge it honestly — tell me whether it's defensible, where it's vague,
and what I clearly don't understand yet. Do NOT explain the code for me first; make me
explain it. At the end, list the weak spots I should go study.
EOF

echo "Created commands in .claude/commands/:"
ls -1 .claude/commands/
echo "Restart Claude Code or type / to see them."
