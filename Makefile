.PHONY: db-migrate db-reset test lint run-eod run-premarket backfill heartbeat

db-migrate:
	python -c "from core.database.client import apply_migrations; print(apply_migrations())"

db-reset:
	@echo "Dropping all tables (dev only)..."
	@python -c "from core.database.client import db_connection; \
	conn = db_connection().__enter__(); \
	cur = conn.cursor(); \
	cur.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public;'); \
	conn.commit()"
	$(MAKE) db-migrate

test:
	pytest tests/

lint:
	ruff check .
	mypy core/ --ignore-missing-imports

run-eod:
	python run_daily_pipeline.py --mode eod

run-premarket:
	python run_daily_pipeline.py --mode premarket

backfill:
	python scripts/backfill.py

heartbeat:
	python scripts/heartbeat_check.py
