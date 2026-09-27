.PHONY: setup demo test check mac server night
setup:
	uv venv --python 3.12
	uv pip install -e '.[dev,river]'
demo:
	.venv/bin/gm-nightly --config examples/fixtures.toml compile
check:
	.venv/bin/ruff check src tests
	.venv/bin/ruff format --check src tests
test:
	.venv/bin/pytest -q
mac:
	./scripts/build-macos.sh
server:
	./scripts/install-server.sh
night:
	.venv/bin/gm-night --config examples/gm-part2.toml run
