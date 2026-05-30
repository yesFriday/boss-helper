# Contributing

## Development Setup

```bash
git clone https://github.com/yesFriday/bosshelper.git
cd bosshelper
pip install -e ".[dev]"
playwright install firefox
```

## Code Style

- Python: follow PEP 8, max line length 120
- HTML/CSS/JS: single file dashboard, keep it readable
- Use `ruff` for linting: `ruff check .`
- No comments unless necessary

## Pull Request Flow

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make changes and test locally
4. Push and open PR against `main`

## Project Conventions

- Backend code lives in `backend/` package
- CLI module lives in `bosshelper_cli/`
- Database migrations are manual ALTER TABLE in `init_db()`
- Frontend is React + TypeScript in `frontend/`
- API returns JSON, CLI outputs JSON envelope

## Testing

```bash
# Manual testing: start server and use web console
python backend/app.py --port 8010

# CLI testing
bosshelper status
bosshelper search "AI Agent" --city 北京
```
