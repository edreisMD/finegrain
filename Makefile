.PHONY: setup demo test check mac server
setup:
	uv venv --python 3.12
	uv pip install -e '.[dev,river]'
demo:
	.venv/bin/finegrain --config examples/fixtures.toml compile
check:
	.venv/bin/ruff check src tests
	.venv/bin/ruff format --check src tests
test:
	.venv/bin/pytest -q
mac:
	./scripts/build-macos.sh
server:
	./scripts/install-server.sh
