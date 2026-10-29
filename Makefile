# Signal engine. Paths are quoted because the project folder name contains spaces.
ROOT := $(CURDIR)
DBT := cd dbt_project && uv run dbt
PROFILE ?= standard

.PHONY: setup generate build calibrate report m1 test app clean

setup:
	uv sync

# make generate NAME=dev SEED=42
generate:
	uv run python -m generator --profile $(PROFILE) --seed $(SEED) --db "data/$(NAME).duckdb"

# make build NAME=dev   (seeds + models + data tests + unit tests)
build:
	$(DBT) build --profiles-dir . --vars '{}' && cd ..
build: export SIGNAL_DB = $(ROOT)/data/$(NAME).duckdb

calibrate:
	uv run python -m eval calibrate --db "data/dev.duckdb"

report:
	uv run python -m eval report --run "dev=data/dev.duckdb:seed 42, thresholds calibrated here" --run "holdout=data/holdout.duckdb:seed 7, headline numbers"

# Full M1 run: dev world → calibrate → rebuild dev → holdout world → report.
m1:
	$(MAKE) generate NAME=dev SEED=42
	$(MAKE) build NAME=dev
	$(MAKE) calibrate
	$(MAKE) build NAME=dev
	$(MAKE) generate NAME=holdout SEED=7
	$(MAKE) build NAME=holdout
	$(MAKE) report

test:
	uv run pytest

# Streamlit app on http://localhost:8501 (needs `make m1` first)
app:
	uv run streamlit run app/streamlit_app/main.py

clean:
	rm -rf data dbt_project/target dbt_project/logs
