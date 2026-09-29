---
name: secrets
description: Protect credential files, signing material, and secrets embedded in outbound URLs.
---

Use this pack whenever an agent can read files or make web requests. It protects local environment files, SSH keys, signing credentials, service-account JSON, and tokens placed in URLs.

Blocked examples include reading `.env.local`, opening an SSH private key, or fetching a URL containing an API key. Allowed examples include reading `.env.example`, source files whose names mention credentials, and ordinary documentation URLs.
