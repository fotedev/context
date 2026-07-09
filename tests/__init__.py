# Test package marker for the context-aggregator repo.
# Pytest auto-discovers tests/* via the `testpaths = ["tests"]` setting in
# pyproject.toml, so this __init__ only exists to make the directory a real
# Python package (helpful when individual test modules need to share imports).