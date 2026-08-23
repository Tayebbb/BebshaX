---
description: "TypeScript and JavaScript coding rules for this project"
applyTo: "**/*.{ts,tsx,js,jsx,mjs,cjs}"
---

# TypeScript / JavaScript Rules

- Strict typing: no `any` unless justified with a comment; prefer explicit return types on exported functions.
- Immutability: spread/copy instead of mutating shared objects and arrays.
- Handle every promise: `await` with try/catch, or explicit `.catch`; no floating promises.
- No `console.log` or `debugger` in committed code; use the project's logger.
- Validate external input at boundaries with the project's validation library.
- Follow the file/module layout of neighboring code; keep files under ~400 lines where practical.
