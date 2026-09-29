---
name: beet
description: Add Beet-specific Codex policy, repository path, and user-record protections.
---

Enable this pack only for Beet coding agents. It protects Beet repository roots, the fleet's Codex approval configuration, and Beet user identifiers sent through URLs.

Blocked examples include editing `.codex/config.toml`, deleting an absolute Beet repository path, or putting a `USR-` record ID in a web URL. Allowed examples include changing an ordinary project config, reading Beet source, and using normal documentation URLs.
