import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools', 'debug'))
import scenes  # noqa: E402


@pytest.mark.skipif(not os.path.exists(scenes.ELF), reason='needs the dumped EBOOT')
def test_stage_table():
    st = scenes.stages()
    assert len(st) == scenes.STAGE_COUNT
    assert st[0] == (0, '1_01_A', 1850, 2032)
    assert st[-1] == (90, '7_11_A', 1905, 2082)
    assert {s[3] for s in st} == set(range(2032, 2083))   # every story script belongs to a stage
