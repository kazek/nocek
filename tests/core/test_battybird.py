import hashlib
import os
from pathlib import Path

import numpy as np
import pytest

from nocek.core import battybird, taxonomy
from nocek.core.battybird import ModelError, ModelFile, interpret
from nocek.core.opinion import Abstention
from nocek.core.taxonomy import Taxon
from tests import synth

LABELS = [
    "Nyctalus noctula",
    "Nyctalus leisleri",
    "Myotis daubentonii",
    "Myotis nattereri",
    "Pipistrellus kuhlii",
    "Pipistrellus nathusii",
    "insect",
    "rain",
]


def scores(*rows: dict[str, float]) -> np.ndarray:
    return np.array([[row.get(label, 0.0) for label in LABELS] for row in rows], np.float32)


def test_every_label_stands_for_catalogued_taxa() -> None:
    known = set(taxonomy.species()) | set(taxonomy.genera())

    for head in battybird.heads().values():
        for taxa in head.bats.values():
            assert taxa <= known
        assert not head.bats.keys() & head.not_a_bat


def test_every_head_has_pinned_files() -> None:
    for head in battybird.heads():
        assert all(len(f.sha256) == 64 for f in battybird.files_for(head))


def test_cuts_a_recording_into_overlapping_windows() -> None:
    # 1 s at 256 kHz: windows start at 0 and 0.42 s; the 40000-sample tail
    # after the second is shorter than a third of a window and dropped.
    windows = battybird.windows_of(synth.audio(synth.noise(1.0)))

    assert windows.shape == (2, battybird.WINDOW)
    assert windows.dtype == np.float32


def test_a_recording_too_short_has_no_windows() -> None:
    assert len(battybird.windows_of(synth.audio(synth.noise(0.1)))) == 0


def test_names_the_best_window_of_the_best_bat() -> None:
    analysis = interpret(scores({"Nyctalus noctula": 0.2}, {"Nyctalus noctula": 0.95}), LABELS)

    assert analysis.opinion.source == battybird.SOURCE
    assert analysis.opinion.taxa == frozenset({Taxon("Nyctalus noctula")})
    assert analysis.opinion.leader is not None
    assert analysis.opinion.leader.score == pytest.approx(0.95)


def test_labels_the_model_cannot_separate_are_merged() -> None:
    analysis = interpret(
        scores({"Myotis daubentonii": 0.8, "Myotis nattereri": 0.9, "Pipistrellus kuhlii": 0.3}),
        LABELS,
    )

    myotis = [c for c in analysis.opinion.ranking if c.taxa == {Taxon("Myotis")}]
    assert len(myotis) == 1
    assert myotis[0].score == pytest.approx(0.9)
    pair = {Taxon("Pipistrellus kuhlii"), Taxon("Pipistrellus nathusii")}
    assert sum(1 for c in analysis.opinion.ranking if c.taxa == pair) == 1


def test_a_weak_best_bat_is_not_named() -> None:
    analysis = interpret(scores({"Nyctalus leisleri": 0.5}), LABELS)

    assert analysis.opinion.abstention is Abstention.NO_MATCH


def test_reports_what_else_it_heard() -> None:
    analysis = interpret(scores({"insect": 0.9, "Nyctalus noctula": 0.8, "rain": 0.1}), LABELS)

    assert [s.label for s in analysis.not_a_bat] == ["insect", "rain"]
    assert analysis.opinion.taxa == frozenset({Taxon("Nyctalus noctula")})


def test_keeps_the_best_bat_of_each_window() -> None:
    analysis = interpret(scores({"Nyctalus noctula": 0.9}, {"Nyctalus leisleri": 0.6}), LABELS)

    assert [w.start_s for w in analysis.windows] == pytest.approx(
        [0.0, battybird.STEP / battybird.SAMPLE_RATE]
    )
    leaders = [w.leader.taxa for w in analysis.windows if w.leader]
    assert leaders == [{Taxon("Nyctalus noctula")}, {Taxon("Nyctalus leisleri")}]


def test_an_unknown_label_is_an_error() -> None:
    with pytest.raises(ModelError, match="Pteropus"):
        interpret(np.zeros((1, 1), np.float32), ["Pteropus vampyrus"])


def test_a_short_recording_needs_no_model(tmp_path: Path) -> None:
    model = battybird.Model(tmp_path / "no-models-here")

    analysis = model.analyse(synth.audio(synth.noise(0.1)))

    assert analysis.opinion.abstention is Abstention.TOO_SHORT


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path, ModelFile]:
    """A local stand-in for the model repository, holding one file."""
    content = b"weights"
    source = tmp_path / "repo" / "weights.tflite"
    source.parent.mkdir()
    source.write_bytes(content)
    model_file = ModelFile("weights.tflite", "weights.tflite", hashlib.sha256(content).hexdigest())
    monkeypatch.setattr(battybird, "files_for", lambda head: [model_file])
    return source.parent.as_uri(), source, model_file


def test_downloads_checks_and_attributes(
    tmp_path: Path, repository: tuple[str, Path, ModelFile]
) -> None:
    url, _, model_file = repository
    target = tmp_path / "models"
    seen: list[int] = []

    battybird.ensure_models(
        target, repository=url, progress=lambda n, done, total: seen.append(done)
    )

    assert (target / model_file.name).read_bytes() == b"weights"
    assert "CC BY-NC-SA 4.0" in (target / "ATTRIBUTION.md").read_text()
    assert seen
    # Present and intact: nothing is downloaded again.
    battybird.ensure_models(target, repository="file:///nowhere")


def test_rejects_a_file_that_does_not_match(
    tmp_path: Path, repository: tuple[str, Path, ModelFile]
) -> None:
    url, source, _ = repository
    source.write_bytes(b"tampered")
    target = tmp_path / "models"

    with pytest.raises(ModelError, match="checksum"):
        battybird.ensure_models(target, repository=url)

    assert list(target.iterdir()) == []


def test_reports_a_failed_download(tmp_path: Path, repository: tuple[str, Path, ModelFile]) -> None:
    with pytest.raises(ModelError, match="download failed"):
        battybird.ensure_models(tmp_path / "models", repository="file:///nowhere")


@pytest.mark.slow
@pytest.mark.skipif(
    "NOCEK_TEST_MODELS" not in os.environ,
    reason="set NOCEK_TEST_MODELS to a directory with the BattyBirdNET files",
)
def test_runs_the_real_model() -> None:
    model = battybird.Model(Path(os.environ["NOCEK_TEST_MODELS"]))

    analysis = model.analyse(synth.audio(synth.sequence(synth.sweep(60, 46, 0.006), n=10)))

    assert len(analysis.windows) == 2
    assert analysis.opinion.leader is not None
