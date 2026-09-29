---
name: git-safety
description: Prevent destructive Git history rewrites, worktree removal, and repository deletion.
---

Enable this pack for coding agents that can run shell commands in a Git checkout. It protects remote history, parallel-agent worktrees, and repository roots.

Blocked examples include force-pushing an unapproved branch, removing a worktree, or recursively deleting the current repository. Allowed examples include status and diff commands, normal feature-branch pushes, force-with-lease on `codex/*` or `feature/*`, and deleting build caches.
