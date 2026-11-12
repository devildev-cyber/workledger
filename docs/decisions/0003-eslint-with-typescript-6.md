# 0003. Use ESLint with TypeScript 6.0 on the frontend

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

The README specifies ESLint for the frontend. The current Vite template uses oxlint with TypeScript 7 instead. typescript-eslint, which ESLint needs for TypeScript, supports TypeScript only up to 6.0.

## Decision

Use ESLint with typescript-eslint, and pin TypeScript to `~6.0`.

## Consequences

- We keep the most widely used linting setup and its plugin ecosystem.
- We do not get TypeScript 7's faster compiler for now.
- Upgrade to TypeScript 7 once typescript-eslint supports it, recording the change in a new decision.
