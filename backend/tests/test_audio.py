from app.audio import parse_silences, plan_segments


def test_short_audio_is_one_segment():
    assert plan_segments(300, [], chunk=600, window=90) == [(0.0, 300)]


def test_no_silence_cuts_on_the_boundary():
    assert plan_segments(1500, [], chunk=600, window=90) == [(0.0, 600), (600, 1200), (1200, 1500)]


def test_cut_lands_in_the_silence_nearest_before_the_boundary():
    silences = [(500.0, 501.0), (580.0, 582.0), (650.0, 651.0)]
    segments = plan_segments(1000, silences, chunk=600, window=90)
    assert segments[0] == (0.0, 581.0)
    # Nooit langer dan een chunk: de stilte ná de grens telt niet.
    assert all(end - start <= 600 for start, end in segments)


def test_silence_outside_the_window_is_ignored():
    segments = plan_segments(1000, [(100.0, 101.0)], chunk=600, window=90)
    assert segments[0] == (0.0, 600)


def test_two_hours_gives_twelve_segments_of_at_most_ten_minutes():
    segments = plan_segments(7200, [], chunk=600, window=90)
    assert len(segments) == 12
    assert segments[-1][1] == 7200


def test_parse_silences_from_ffmpeg_log():
    log = """
[silencedetect @ 0x1] silence_start: 1.5
[silencedetect @ 0x1] silence_end: 2.25 | silence_duration: 0.75
[silencedetect @ 0x1] silence_start: -0.01
[silencedetect @ 0x1] silence_end: 0.5 | silence_duration: 0.51
"""
    assert parse_silences(log) == [(1.5, 2.25), (0.0, 0.5)]
