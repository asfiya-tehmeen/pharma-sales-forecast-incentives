import pytest

from fairtargets import generator, warehouse


@pytest.fixture(scope="session")
def world():
    return generator.generate(seed=42)


@pytest.fixture(scope="session")
def built(world, tmp_path_factory):
    """Write the generated world to a temp folder and build a warehouse from it."""
    root = tmp_path_factory.mktemp("run")
    raw = root / "raw"
    generator.write(world, raw)
    con = warehouse.build(raw=raw, db_path=root / "wh.duckdb")
    yield con
    con.close()
