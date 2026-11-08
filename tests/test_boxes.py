"""Width gate data: every entry to translate has a pixel budget, and unseen entries borrow their table's classes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boxes  # noqa: E402
from insert import load  # noqa: E402


def entries():
    for sub in ('story', 'common', 'eboot'):
        for es in load(sub).values():
            yield from (e for e in es if e.get('jp') and e.get('status') != 'data')


def test_every_entry_has_a_budget():
    missing = [e['id'] for e in entries() if boxes.budget(e) is None]
    assert not missing, missing[:20]


def test_every_seen_class_is_measured_or_tagged():
    for k in {k for ks in boxes.classes().values() for k in ks}:
        assert k in boxes.BUDGETS, k
        assert boxes.BUDGETS[k][2].split(':')[0] in ('measured', 'guess'), k


def test_table_lends_classes():
    # the card name table (e:2bcf44 seen in the treasure bubble) lends its class to its neighbour e:2bcf4f
    got = boxes.table_classes(boxes.classes())
    assert '1/15/20/2' in got.get('e:2bcf4f', []), got.get('e:2bcf4f')
    b = boxes.budget({'id': 'e:2bcf4f', 'slots': ['w:2bd200']})
    assert b and not b[3]   # borrowed: not measured for this entry
