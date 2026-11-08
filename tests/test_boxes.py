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


def test_unit_record_fields():
    """HUD (72 px) draws a record's short name, else its full name; team names go to the full map lists; the place
    list after the records is not HUD text."""
    e = {x['id']: x for x in entries()}
    k = lambda i: boxes.budget(e[i])[2]   # noqa: E731
    assert k('e:280cdc') == boxes.HUD and boxes.budget(e['e:280cdc'])[3]   # コブン, short name of record 47: measured
    assert k('e:281048') == boxes.HUD                                     # 謎の女: no short name -> full name
    assert k('e:280c10') != boxes.HUD                                     # 皇国騎兵: has a short name (コウコクキ兵)
    assert boxes.TEAM in boxes.record_classes(e['e:280944'])              # Minesota Unit: team name
    assert k('e:281a10') == '1/15/20/1'                                   # 加工都市アレン: place list


def test_row_of_shared_window():
    e = {x['id']: x for x in entries()}
    assert boxes.budget(e['e:256a10'])[:3] == (290, 1, '2/22/14/1')      # skill effect: line 1
    assert boxes.budget(e['e:257084'])[:3] == (225, 2, '2/22/14/2')      # use condition: line 2


def test_fewest_lines_of_all_windows():
    """An entry drawn in a 1-row window (VS skill tag) gets 1 line even if a 5-row list shows it too: a second row
    writes past the window's cells (the battle_result crash, "Strong Attack\\ndamage up")."""
    e = {x['id']: x for x in entries()}
    assert boxes.budget(e['e:2560bc'])[:2] == (145, 1)


def test_balanced_wrap_and_stub_rule():
    """Greedy wrap left one-word widows ("...let me take you\\nin."): the wrap keeps the greedy line count and evens
    the lines out; the lint flags a short line ending a sentence the line above runs into."""
    import batches
    import vwf
    t = "Well, they're handing these out, aren't they? So come quietly and let me take you in."
    rows = batches.wrap(t, 288, 1).split("\n")
    assert len(rows) == 3 and all(vwf.line_px(r, 1) <= 288 for r in rows) and len(rows[-1]) >= 6
    assert " ".join(rows) == t
    assert batches.stub(["So come quietly and let me take you", "in."]) == "in."
    assert batches.stub(["Hmm...", "Yes."]) is None
