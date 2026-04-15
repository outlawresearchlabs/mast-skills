# Prompt Templates

## /review-pr
Review the most recent pull request against style guide and best practices.
Check: code quality, test coverage, security issues, naming conventions.
VERIFICATION STEP: Before delivering, run linter + tests and verify against acceptance criteria.

## /deploy-check
Verify deployment readiness for the current branch.
Check: all tests pass, no open security vulnerabilities, config is valid.
VERIFICATION STEP: Before delivering, confirm all acceptance criteria are met and no TODOs remain.

## /verify
Run the full verification protocol from the operational rules:
1. Check low-level correctness (lint, tests, compilation)
2. Check high-level objective alignment (does this solve the actual problem?)
3. Check for step repetition issues (FM-1.3)
4. Check for task derailment issues (FM-2.3)
5. Report findings

## /status
Summarize: what has been done, what remains, what is blocked.
Surfaces FM-1.3, FM-1.5, and FM-2.3 issues early.
