---
name: publishing
description: Guard production releases, registry publishing, store uploads, and production database changes.
---

Enable this pack for agents with release, package-manager, deployment, or database tooling. It prevents irreversible publication and production changes from being performed as routine coding work, and asks for human approval when the command alone does not establish a safe context.

Blocked examples include pushing a production branch, deploying with a production flag, publishing to npm, uploading an app, or applying a Prisma schema to production. Allowed examples include draft pull requests, development migrations, staging deploys, tests, and listing existing builds.

Approval-required examples include merging a pull request without an explicit non-production base, creating a GitHub release, and upload or publish commands not already covered by a blocking rule. Blocking rules take precedence when both tiers match.
