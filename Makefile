.PHONY: setup refresh build workbook figures tableau app test lint

setup:
	uv sync

refresh:
	uv run python -m livingry.fetch

build:
	uv run python -m livingry.build

workbook:
	uv run python -m livingry.workbook

figures:
	uv run python -m livingry.figures

tableau:
	uv run python -m livingry.tableau_workbook

app:
	uv run streamlit run app/streamlit_app.py

test:
	uv run pytest -q

lint:
	uv run ruff check src tests app

all: refresh build workbook figures tableau test
