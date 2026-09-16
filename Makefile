.PHONY: help db-migrate db-reset backfill test lint run-eod run-premarket clean

help:
	@echo "Targets: db-migrate, db-reset, backfill, test, lint, run-eod, run-premarket, clean"

db-migrate:
	@echo "Apply migrations in order via Supabase SQL editor."
	@ls -1 migrations/*.sql | sort

db-reset:
	@echo "Drop and recreate all tables (DEV ONLY)."
	@psql $$SUPABASE_DB_URL -f scripts/drop_all.sql

backfill:
	python scripts/backfill.py

test:
	pytest tests/ -v --cov=core --cov-report=term-missing

lint:
	ruff check .
	mypy core/ --strict

run-eod:
	python run_daily_pipeline.py --mode eod

run-premarket:
	python run_daily_pipeline.py --mode premarket

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -name "*.pyc" -delete
