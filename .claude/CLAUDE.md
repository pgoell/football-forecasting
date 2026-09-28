# football-forecasting: project instructions

Predict football matches with statistical models, then test whether the forecasts beat the betting market after costs.

## Project notes

The project's notes live in the Kasten vault, folder `02 Projects/Football Forecasting/`:

- `Football Forecasting.md`: goal, first milestone, phases
- `Experiment Spec.md`: Phase 0 rules (questions, scope, data split, metrics, success criteria)
- `ChatGPT Predict Football Games.md`: the chat the project started from, verbatim

How to reach them:

1. On the VPS, read them from disk: `/home/pascal/kasten-data/vault/02 Projects/Football Forecasting/`
2. Anywhere else, or when writing notes, use the Kasten MCP (`list_notes`, `read_note`, `search_notes`, `save_note`, `append_note`) with the vault path above, e.g. `02 Projects/Football Forecasting/Experiment Spec.md`. Read `99 Misc/01 Config/reading-this-vault.md` before writing.

Write vault notes through the Kasten MCP, never by editing the files on disk: it handles frontmatter and conflict checks.

The vault's `Experiment Spec.md` is the master. `docs/experiment-spec.md` is a copy for the repo; when the vault spec changes, update the copy in the same PR.

## Layout

- `src/football_forecasting/`: the package
- `tests/`: pytest
- `docs/`: experiment spec copy

## Commands

mise owns every command. `mise tasks` lists them.

```sh
mise run install        # git hooks + dependencies
mise run test           # pytest
mise run lint           # ruff check, ruff format --check, ty check
mise run fmt            # ruff format
mise run check-commits  # cocogitto on unpushed commits
```

## Conventions

- Conventional Commits (`feat:`, `fix:`, `chore:` ...). The `commit-msg` hook rejects anything else.
- Never tune anything on the holdout seasons. Read the spec's "Rules against fooling ourselves" before touching models or metrics.
