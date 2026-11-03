# Scope: 261105-review-rounds

## Purpose and users

Background: The export command writes one file per run and overwrites the last one.

Purpose: Keep every export by adding a dated name, and ship it as 1.4.0.

Users: the people who export reports.

## Completion criteria

1. Each export gets a dated file name. [check: command]
2. An existing export is never overwritten. [check: command]
3. The docs name the new file pattern. [check: file]

## Non-goals

- No change to the file format.
