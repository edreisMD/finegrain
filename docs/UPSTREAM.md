# Upstream contracts

Verified against **garrytan/gbrain 0.59.0.0**, commit `e78f1c38b947b053f3a46881340f74f316be855a`, the `latest-stable` target fetched during implementation. Installer and Docker image pin this commit. Existing installations are preserved.

- [Official standalone installation](https://github.com/garrytan/gbrain/blob/master/docs/INSTALL.md): canonical GitHub Bun distribution; `init --pglite --no-embedding` for a fresh personal brain.
- [Company-brain setup](https://github.com/garrytan/gbrain/blob/master/docs/tutorials/company-brain.md): Postgres, sources, per-person OAuth, source grants, and bounded write prefixes.
- [Remote server](https://github.com/garrytan/gbrain/blob/master/docs/mcp/DEPLOY.md): `serve --http`, official `/admin/` dashboard, machine OAuth, TLS publication.
- [Page operations](https://github.com/garrytan/gbrain/blob/master/src/core/ops/pages.ts): `get_page`, `list_pages`, `put_page`, `delete_page`; revisions and durable request IDs. Use `gbrain call list_pages '<JSON>'` for machine-readable lists: this release's `gbrain list --json` still uses its tabular formatter.
- [Transcript ingestion](https://github.com/garrytan/gbrain/blob/master/src/commands/transcripts.ts): native Claude/Codex import, `--since last`, explicit source, embeddings off by default. Finegrain does not reimplement their brain ingestion system.
- [Agent Sessions](https://github.com/jazzyalex/agent-sessions): useful precedent for read-only local session discovery and per-harness parsers. Finegrain's code is independently implemented; no vendored source.
- [Pi session schema](https://pi.dev/docs/latest/session-format) and [implementation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/session-manager.ts): JSONL, `id`/`parentId` branches, text blocks, context edits. Finegrain follows the most recently persisted branch; branch navigation without another persisted event cannot be inferred from the file alone.
- [Claude hooks](https://code.claude.com/docs/en/hooks): sessions and transcript paths. Gbrain has native hooks already; Finegrain does not overwrite unrelated harness settings.
- [River SDK](https://docs.river.ai): `river-client==0.11.0`, actual SDK renderers, training clients, rollout environments, and asynchronous trainer. Provider calls are covered by contract tests.

The hosted gbrain.io product also has export docs, but those are not the installation contract for the open-source personal/company runtime used here.
