from app.turns import Segment, merge_turns, normalize, speakers_of, split_long


def test_merges_same_speaker_and_keeps_short_interjections():
    found = [
        Segment(0.0, 4.0, "A"),
        Segment(4.2, 4.6, "B"),  # "ja": hoort bij de beurt van A
        Segment(4.8, 9.0, "A"),
        Segment(9.5, 15.0, "B"),
        Segment(15.0, 20.0, "B"),
    ]
    turns = merge_turns(found)
    assert [(t.speaker, t.start, t.end) for t in turns] == [("A", 0.0, 9.0), ("B", 9.5, 20.0)]


def test_merge_sorts_and_skips_empty_segments():
    turns = merge_turns([Segment(5, 8, "B"), Segment(0, 4, "A"), Segment(3, 3, "C")])
    assert [t.speaker for t in turns] == ["A", "B"]


def test_split_long_turn_in_a_silence():
    turns = [Segment(10.0, 40.0, "A"), Segment(40.0, 45.0, "B")]
    pieces = split_long(turns, silences=[(27.0, 29.0)], chunk=20, window=5)
    assert [(p.speaker, p.start, p.end) for p in pieces] == [
        ("A", 10.0, 28.0),
        ("A", 28.0, 40.0),
        ("B", 40.0, 45.0),
    ]


def test_normalize_numbers_speakers_by_first_appearance():
    segs = [
        Segment(5, 8, "SPEAKER_00", "Hallo, ik heb een vraag."),
        Segment(0, 5, "SPEAKER_01", "Goedemiddag, servicedesk."),
        Segment(8, 9, "SPEAKER_00", " Over mijn factuur. "),
        Segment(9, 10, "SPEAKER_02", "   "),
    ]
    out = normalize(segs)
    assert [(s.speaker, s.text) for s in out] == [
        ("S1", "Goedemiddag, servicedesk."),
        ("S2", "Hallo, ik heb een vraag. Over mijn factuur."),
    ]
    assert out[1].end == 9
    assert speakers_of(out) == ["S1", "S2"]
