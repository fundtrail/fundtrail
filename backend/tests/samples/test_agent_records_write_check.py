"""Every agent record in the sample packs passes the save's write check (ruling 69).

The checks-only play stores agent_records.json straight into the database, so it never
runs the write check a real save runs. data/test_write_check.py does, over both samples;
this runs it in CI.
"""

import importlib.util
from types import ModuleType

from app.samples.pack import DATA_DIR


def _write_check() -> ModuleType:
    path = DATA_DIR / "test_write_check.py"
    spec = importlib.util.spec_from_file_location("data_test_write_check", path)
    assert spec is not None and spec.loader is not None, f"can't load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_agent_record_passes_the_write_check() -> None:
    check = _write_check()
    seed = check.test_seed
    generated = seed.gen()
    problems: list[str] = []
    for folder in (seed.LARGER, seed.SMALL):
        problems += check.write_check_problems(folder, generated[folder])
    assert not problems, "agent_records.json fails the write check:\n" + "\n".join(problems)
