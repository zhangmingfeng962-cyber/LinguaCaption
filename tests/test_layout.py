import random

from linguacaption.core.layout import Rect, place_subtitle


def test_moves_above_original_subtitle_area():
    bounds = Rect(0, 0, 1920, 1080)
    safe = Rect(0, 850, 1920, 230)
    result = place_subtitle(bounds, (700, 120), (610, 900), [safe])
    assert result is not None
    assert bounds.contains(result)
    assert not result.intersects(safe.padded(12))
    assert result.bottom <= 838


def test_impossible_placement_hides_instead_of_covering():
    assert place_subtitle(Rect(0, 0, 400, 300), (250, 100), (50, 170), [Rect(0, 0, 400, 300)]) is None


def test_negative_monitor_coordinates_and_narrow_corridor():
    bounds = Rect(-1920, -100, 1920, 1080)
    safe = [Rect(-1920, -100, 800, 1080), Rect(-400, -100, 400, 1080)]
    result = place_subtitle(bounds, (650, 120), (-1900, 700), safe)
    assert result is not None and bounds.contains(result)
    assert all(not result.intersects(r.padded(12)) for r in safe)


def test_random_placements_always_respect_protected_areas():
    rng = random.Random(184)
    bounds = Rect(-1280, 0, 1280, 720)
    for _ in range(300):
        safe = [Rect(rng.randrange(-1280, -100), rng.randrange(0, 600),
                     rng.randrange(40, 300), rng.randrange(40, 180)) for _ in range(4)]
        result = place_subtitle(bounds, (380, 140), (-850, 500), safe)
        if result:
            assert bounds.contains(result)
            assert all(not result.intersects(r.padded(12)) for r in safe)
