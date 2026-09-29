"""Beet fleet safety rules for coding-agent tool calls."""

from agent.warden import Rule


SHELL_TOOLS = r"^(?:Bash|exec|shell)$"
FILE_AND_SHELL_TOOLS = r"^(?:Bash|exec|shell|Read|Edit|Write|read_file|list_directory)$"
WEB_TOOLS = r"^(?:web_fetch|web_search)$"


BEET_RULES: list[Rule] = [
    Rule(
        id="beet-permissions-codex-settings",
        family="permissions",
        tool=r"^(?:Edit|Write)$",
        pattern=r"(?:^|[/\\])\.codex[/\\](?:config\.toml|rules(?:[/\\]|[\"']))",
        reason="Prevents agents from weakening Codex approval settings or prompt rules.",
    ),
    Rule(
        id="beet-permissions-shell-mutation",
        family="permissions",
        tool=SHELL_TOOLS,
        pattern=(
            r"\A(?s:(?=.*(?:^|[/\\])\.codex[/\\](?:config\.toml|rules[/\\]))"
            r"(?=.*(?:\brm\b|\bmv\b|\btruncate\b|\bsed\s+-i\b|\bperl\s+-pi\b|>>?|\btee\b))"
            r")"
        ),
        reason="Prevents shell commands from changing Codex approval settings or deleting prompt rules.",
    ),
    Rule(
        id="beet-secrets-dotfiles",
        family="secrets",
        tool=FILE_AND_SHELL_TOOLS,
        pattern=(
            r"(?:^|[/\\])(?:\.sentryclirc|\.netrc)\b|"
            r"(?:^|[/\\])\.env(?!\.(?:example|sample|template)(?=$|[/\\\"'\s]))"
            r"(?:\.[A-Za-z0-9_-]+)?(?=$|[/\\\"'\s])"
        ),
        reason="Protects local token files and non-template environment files from agent access.",
    ),
    Rule(
        id="beet-secrets-private-keys",
        family="secrets",
        tool=FILE_AND_SHELL_TOOLS,
        pattern=(
            r"(?:^|[/\\])id_(?:rsa|ecdsa|ed25519)"
            r"(?!\.pub(?=$|[/\\\"'\s]))(?:\.[A-Za-z0-9_-]+)?(?=$|[/\\\"'\s])"
        ),
        reason="Protects SSH private keys from agent access.",
    ),
    Rule(
        id="beet-secrets-signing-material",
        family="secrets",
        tool=FILE_AND_SHELL_TOOLS,
        pattern=r"\.(?:p8|p12|mobileprovision)(?=$|[/\\\"'\s])",
        reason="Protects Apple signing keys, certificates, and provisioning profiles.",
    ),
    Rule(
        id="beet-secrets-credential-json",
        family="secrets",
        tool=FILE_AND_SHELL_TOOLS,
        pattern=r"(?:^|[/\\])[^/\\\"']*(?:service[-_]?account|credentials)[^/\\\"']*\.json\b",
        reason="Protects service-account and credential JSON files.",
    ),
    Rule(
        id="beet-git-force-push",
        family="git-history",
        tool=SHELL_TOOLS,
        pattern=(
            r"\bgit\s+push(?=(?:\\.|[^\"\\\r\n])*"
            r"(?:--force(?!-with-lease)(?:\b|=)|(?<!\S)-f(?!\S)))"
        ),
        reason="Blocks force pushes that can rewrite remote Git history.",
    ),
    Rule(
        id="beet-git-force-lease-protected",
        family="git-history",
        tool=SHELL_TOOLS,
        pattern=(
            r"\bgit\s+push(?=(?:\\.|[^\"\\\r\n])*--force-with-lease(?:\b|=))"
            r"(?=(?:\\.|[^\"\\\r\n])*[\s:=](?:\\\"|[\"'])?(?:refs/heads/)?"
            r"(?:main|master|develop|production|release(?:[/_-][\w.-]+)?)"
            r"(?=(?:\\\"|[\s:\"'])))"
        ),
        reason="Blocks force-with-lease pushes to protected branches.",
    ),
    Rule(
        id="beet-git-force-lease-unapproved",
        family="git-history",
        tool=SHELL_TOOLS,
        pattern=(
            r"\bgit\s+push(?=(?:\\.|[^\"\\\r\n])*--force-with-lease(?:\b|=))"
            r"(?!(?:\\.|[^\"\\\r\n])*(?:codex|feature)/[A-Za-z0-9._/-]+"
            r"(?=(?:\\\"|[\s:\"'])))"
        ),
        reason="Allows force-with-lease only on codex/* or feature/* branches.",
    ),
    Rule(
        id="beet-production-pr-merge",
        family="production-release",
        tool=SHELL_TOOLS,
        pattern=(
            r"\bgh\s+pr\s+merge\b(?:\\.|[^\"\\\r\n])*--base(?:=|\s+)(?:\\\"|[\"'])?"
            r"(?:main|master|production|release(?:[/_-][\w.-]+)?)(?=(?:\\\"|[\s\"']))"
        ),
        reason="Blocks pull-request merges explicitly targeting a production base branch.",
    ),
    Rule(
        id="beet-production-git-push",
        family="production-release",
        tool=SHELL_TOOLS,
        pattern=(
            r"\bgit\s+push\b(?:\\.|[^\"\\\r\n])*[\s:=](?:\\\"|[\"'])?(?:refs/heads/)?"
            r"(?:main|master|production|release(?:[/_-][\w.-]+)?)(?=(?:\\\"|[\s:\"']))"
        ),
        reason="Blocks direct Git pushes to production branches.",
    ),
    Rule(
        id="beet-production-deploy",
        family="production-release",
        tool=SHELL_TOOLS,
        pattern=(
            r"(?:\bdeploy\b(?:\\.|[^\"\\\r\n])*(?:--prod(?:uction)?\b|\bprod(?:uction)?\b)|"
            r"\bvercel\b(?:\\.|[^\"\\\r\n])*--prod\b)"
        ),
        reason="Blocks commands that deploy the Beet application to production.",
    ),
    Rule(
        id="beet-deletion-worktree",
        family="deletion",
        tool=SHELL_TOOLS,
        pattern=r"\bgit\s+worktree\s+remove\b",
        reason="Blocks removal of Git worktrees used by parallel coding agents.",
    ),
    Rule(
        id="beet-deletion-repository",
        family="deletion",
        tool=SHELL_TOOLS,
        pattern=(
            r"\brm\s+(?:-[A-Za-z]*r[A-Za-z]*f[A-Za-z]*|-[A-Za-z]*f[A-Za-z]*r[A-Za-z]*)\s+"
            r"(?:--\s+)?(?:\\\"|[\"'])?(?:"
            r"\.(?:/)?(?=(?:\\\"|[\s;&|\"']|$))|\$PWD\b|\$\(pwd\)|"
            r"\$\(git\s+rev-parse\s+--show-toplevel\)|"
            r"(?:\\.|[^\"'\r\n])*(?:/|^)(?:Beet|agent-warden)/?"
            r"(?=(?:\\\"|[\s;&|\"']|$)))"
        ),
        reason="Blocks recursive deletion of a repository directory.",
    ),
    Rule(
        id="beet-publishing-npm",
        family="publishing",
        tool=SHELL_TOOLS,
        pattern=r"\bnpm\s+publish\b",
        reason="Blocks publishing a package to the npm registry.",
    ),
    Rule(
        id="beet-publishing-fastlane",
        family="publishing",
        tool=SHELL_TOOLS,
        pattern=r"\bfastlane\s+(?:pilot|deliver)\b(?:\\.|[^\"\\\r\n])*\bupload\b",
        reason="Blocks Fastlane uploads to TestFlight or the App Store.",
    ),
    Rule(
        id="beet-publishing-altool",
        family="publishing",
        tool=SHELL_TOOLS,
        pattern=r"\bxcrun\s+altool\b(?:\\.|[^\"\\\r\n])*--upload-app\b",
        reason="Blocks direct application uploads through Apple's altool.",
    ),
    Rule(
        id="beet-publishing-app-store",
        family="publishing",
        tool=SHELL_TOOLS,
        pattern=r"\b(?:app[ -]?store|testflight)\b(?:\\.|[^\"\\\r\n])*\b(?:submit|submission|upload)\b",
        reason="Blocks App Store and TestFlight submission commands.",
    ),
    Rule(
        id="beet-database-production",
        family="database",
        tool=SHELL_TOOLS,
        pattern=(
            r"\bprisma\s+(?:migrate\s+deploy|db\s+push)\b[^\r\n]{0,400}?"
            r"(?:\bprod(?:uction)?\b|PRODUCTION_DATABASE_URL|DATABASE_URL=[^\s\"']{0,200}?prod)"
            r"|(?:\bprod(?:uction)?\b|PRODUCTION_DATABASE_URL|DATABASE_URL=[^\s\"']{0,200}?prod)"
            r"[^\r\n]{0,400}?\bprisma\s+(?:migrate\s+deploy|db\s+push)\b"
        ),
        reason="Blocks Prisma schema changes against a production database.",
    ),
    Rule(
        id="beet-network-secret-url",
        family="network-exfiltration",
        tool=WEB_TOOLS,
        pattern=(
            r"https?://[^\"\s]*(?:sk_(?:live|test)_[A-Za-z0-9_-]{8,}|"
            r"bearer(?:=|:|%3[aA]|%20|/)[A-Za-z0-9._~%+-]{8,}|"
            r"(?:access[_-]?token|api[_-]?key)(?:=|%3[dD]|/)[A-Za-z0-9._~%+-]{8,})"
        ),
        reason="Blocks web requests that place API keys or bearer tokens in a URL.",
    ),
    Rule(
        id="beet-network-user-record-url",
        family="network-exfiltration",
        tool=WEB_TOOLS,
        pattern=r"https?://[^\"\s]*(?:/|=|%2[fF])USR-\d+\b",
        reason="Blocks web requests that expose Beet user record identifiers in a URL.",
    ),
]
