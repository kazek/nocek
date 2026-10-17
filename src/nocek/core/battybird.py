"""Identify species with BattyBirdNET, a second network trained on other data.

BattyBirdNET (Zinck, 2023) is BirdNET with a classifier head trained on bats.
BirdNET turns 144000 samples into 1024 numbers and the head maps those to
classes. Bat calls reach a network built for birds by redefining the sample
rate: 0.5625 s at 256 kHz is the same tensor as 3 s at 48 kHz.

It shares nothing with BatDetect2 or the field key: different architecture,
training data and country. The Bavaria head knows the Central European bats
BatDetect2 lacks, has classes for sounds that are not bats, and scores every
class independently, so on noise all of them can stay near zero instead of
one being forced to win.

The weights are licensed CC BY-NC-SA 4.0 and are downloaded, with their
attribution, by `ensure_models`.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import numpy.typing as npt
import soxr

from nocek.core import taxonomy
from nocek.core._data import load_json
from nocek.core.audio import Audio
from nocek.core.opinion import Abstention, Candidate, Opinion
from nocek.core.taxonomy import Taxon

SOURCE = "battybirdnet"

SAMPLE_RATE = 256_000
WINDOW = 144_000  # samples the network takes: 0.5625 s at 256 kHz
STEP = WINDOW * 3 // 4  # windows overlap by a quarter
MIN_TAIL = WINDOW // 3  # a shorter last window is dropped, a longer one padded

Scores = npt.NDArray[np.float32]

# The weights come from one fixed commit, and every file is checked against
# its checksum, so a changed model upstream fails loudly instead of quietly
# shifting every name.
REPOSITORY = (
    "https://raw.githubusercontent.com/rdz-oss/BattyBirdNET-Analyzer/"
    "64c458f4576fe960bf11e34035ebf206374c6299"
)
EMBEDDING = "BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite"


@dataclass(frozen=True)
class ModelFile:
    name: str
    path: str  # in the repository
    sha256: str


FILES = {
    f.name: f
    for f in (
        ModelFile(
            EMBEDDING,
            "checkpoints/V2.4/BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite",
            "55f3e4055b1a13bfa9a2452731d0d34f6a02d6b775a334362665892794165e4c",
        ),
        ModelFile(
            "BattyBirdNET-Bavaria-256kHz.tflite",
            "checkpoints/bats/v1.0/BattyBirdNET-Bavaria-256kHz.tflite",
            "c87d23ce2bf35637a086aa3ed1b1d03b55dd1f111af1d1571460e0c43b98e210",
        ),
        ModelFile(
            "BattyBirdNET-Bavaria-256kHz_Labels.txt",
            "checkpoints/bats/v1.0/BattyBirdNET-Bavaria-256kHz_Labels.txt",
            "ff4a3f9a351f202c8712c807c6bb8b29df0b1c75ddab48e543ec76a88a42715c",
        ),
    )
}

ATTRIBUTION = """\
# BattyBirdNET model weights

Downloaded by Nocek. Not part of Nocek and not covered by its licence.

- BattyBirdNET-Analyzer: Zinck, R.D. (2023). BattyBirdNET - Bat Sound Analyzer.
  https://github.com/rdz-oss/BattyBirdNET-Analyzer
- Built on BirdNET: Kahl, S. et al., Cornell Lab of Ornithology and Chemnitz
  University of Technology.
- Licence: CC BY-NC-SA 4.0, https://creativecommons.org/licenses/by-nc-sa/4.0/

Non-commercial use only. If these files are passed on, this file goes with them.
"""

Progress = Callable[[str, int, int], None]  # file name, bytes done, bytes total


@dataclass(frozen=True)
class Params:
    head: str = "Bavaria"
    # BattyBirdNET's own default for reporting a detection.
    min_score: float = 0.7
    # A species that rarely occurs in a region must score at least this.
    rare_min_score: float = 0.95
    # Interpreter threads; None uses every core.
    threads: int | None = None


DEFAULT_PARAMS = Params()


@dataclass(frozen=True)
class Head:
    bats: Mapping[str, frozenset[Taxon]]
    not_a_bat: frozenset[str]


@dataclass(frozen=True)
class Sound:
    """A class that is not a bat, and its score."""

    label: str
    score: float


@dataclass(frozen=True)
class Window:
    """The best bat in one window of the recording."""

    start_s: float
    leader: Candidate | None


@dataclass(frozen=True)
class Analysis:
    opinion: Opinion
    # Non-bat classes among the five best-scoring classes, best first.
    not_a_bat: tuple[Sound, ...]
    windows: tuple[Window, ...]


class ModelError(Exception):
    """The model files are missing, damaged, or do not belong together."""


@cache
def heads() -> Mapping[str, Head]:
    return MappingProxyType(
        {
            name: Head(
                bats=MappingProxyType(
                    {
                        label: frozenset(taxonomy.get(t) for t in taxa)
                        for label, taxa in h["bats"].items()
                    }
                ),
                not_a_bat=frozenset(h["not_a_bat"]),
            )
            for name, h in load_json("battybird_labels.json")["heads"].items()
        }
    )


def files_for(head: str) -> list[ModelFile]:
    return [
        FILES[EMBEDDING],
        FILES[f"BattyBirdNET-{head}-256kHz.tflite"],
        FILES[f"BattyBirdNET-{head}-256kHz_Labels.txt"],
    ]


def ensure_models(
    directory: Path,
    head: str = DEFAULT_PARAMS.head,
    progress: Progress | None = None,
    repository: str = REPOSITORY,
) -> None:
    """Download whatever model files are missing or damaged, and check them all.

    A file is written beside its final name and renamed only once its checksum
    matches, so an interrupted download never looks like a finished one.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for f in files_for(head):
        target = directory / f.name
        if target.is_file() and _sha256(target) == f.sha256:
            continue
        partial = target.with_name(target.name + ".part")
        try:
            _download(f"{repository}/{f.path}", partial, f.name, progress)
            if _sha256(partial) != f.sha256:
                raise ModelError(f"{f.name}: downloaded file does not match its checksum")
            partial.replace(target)
        except OSError as error:
            raise ModelError(f"{f.name}: download failed: {error}") from error
        finally:
            partial.unlink(missing_ok=True)
    (directory / "ATTRIBUTION.md").write_text(ATTRIBUTION, "utf-8")


def windows_of(audio: Audio) -> npt.NDArray[np.float32]:
    """The recording at 256 kHz, cut into the network's overlapping windows."""
    samples = soxr.resample(audio.samples, audio.sample_rate, SAMPLE_RATE, quality="HQ")
    # The same length librosa gives, so results match its resampling exactly.
    n = int(np.ceil(len(audio.samples) * SAMPLE_RATE / audio.sample_rate))
    samples = np.pad(samples, (0, max(0, n - len(samples))))[:n].astype(np.float32)

    out = []
    for start in range(0, len(samples), STEP):
        window = samples[start : start + WINDOW]
        if len(window) < MIN_TAIL:
            break
        # Zeros rather than noise, so a recording always gets the same answer.
        out.append(np.pad(window, (0, WINDOW - len(window))))
    return np.array(out, dtype=np.float32).reshape(-1, WINDOW)


def interpret(scores: Scores, labels: Sequence[str], params: Params = DEFAULT_PARAMS) -> Analysis:
    """One recording's opinion from per-window scores (windows x labels).

    A class scores its best window, not its mean: a bat crosses the
    microphone for a fraction of a recording, and averaging over the empty
    rest would bury it.
    """
    head = heads()[params.head]
    unknown = set(labels) - head.bats.keys() - head.not_a_bat
    if unknown:
        raise ModelError(f"labels missing from battybird_labels.json: {sorted(unknown)}")

    best = scores.max(axis=0)
    by_taxa: dict[frozenset[Taxon], float] = {}
    for label, score in zip(labels, best, strict=True):
        if label in head.bats:
            taxa = head.bats[label]
            by_taxa[taxa] = max(by_taxa.get(taxa, 0.0), float(score))
    ranking = sorted(
        (Candidate(taxa=taxa, score=score) for taxa, score in by_taxa.items()),
        key=lambda c: -c.score,
    )

    top_five = sorted(range(len(labels)), key=lambda i: -best[i])[:5]
    not_a_bat = tuple(
        Sound(labels[i], float(best[i])) for i in top_five if labels[i] in head.not_a_bat
    )
    return Analysis(
        opinion=Opinion(
            source=SOURCE,
            ranking=tuple(ranking),
            min_score=params.min_score,
            shortlist_ratio=1.0,
        ),
        not_a_bat=not_a_bat,
        windows=tuple(
            Window(start_s=i * STEP / SAMPLE_RATE, leader=_window_leader(row, labels, head))
            for i, row in enumerate(scores)
        ),
    )


class Model:
    """BattyBirdNET, loaded on first use from a directory of model files."""

    def __init__(self, directory: Path, params: Params = DEFAULT_PARAMS) -> None:
        self.directory = directory
        self.params = params
        self._net: _Net | None = None

    def analyse(self, audio: Audio) -> Analysis:
        windows = windows_of(audio)
        if not len(windows):
            return Analysis(
                opinion=Opinion(
                    source=SOURCE,
                    ranking=(),
                    min_score=self.params.min_score,
                    shortlist_ratio=1.0,
                    declined=Abstention.TOO_SHORT,
                ),
                not_a_bat=(),
                windows=(),
            )
        if self._net is None:
            self._net = _Net(self.directory, self.params)
        return interpret(self._net.scores(windows), self._net.labels, self.params)


class _Net:
    """The embedding network and the classifier head, as two interpreters."""

    def __init__(self, directory: Path, params: Params) -> None:
        from ai_edge_litert.interpreter import Interpreter

        embedding, head, labels = (directory / f.name for f in files_for(params.head))
        for path in (embedding, head, labels):
            if not path.is_file():
                raise ModelError(f"{path.name} is missing from {directory}")
        threads = params.threads or os.cpu_count() or 1

        # The embedding is an intermediate tensor, the one feeding BirdNET's
        # own classification layer; preserving all tensors keeps it readable.
        # That is also what BattyBirdNET does, so its debugging-only warning
        # tells the user nothing.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*experimental_preserve_all_tensors")
            self.embedding = Interpreter(
                model_path=str(embedding),
                num_threads=threads,
                experimental_preserve_all_tensors=True,
            )
        self.embedding.allocate_tensors()
        self.embedding_in = self.embedding.get_input_details()[0]["index"]
        self.embedding_out = self.embedding.get_output_details()[0]["index"] - 1

        self.head = Interpreter(model_path=str(head), num_threads=threads)
        self.head.allocate_tensors()
        self.head_in = self.head.get_input_details()[0]["index"]
        self.head_out = self.head.get_output_details()[0]["index"]
        self.width = int(self.head.get_input_details()[0]["shape"][-1])

        self.labels = [
            line.strip().split("_")[0]
            for line in labels.read_text("utf-8").splitlines()
            if line.strip()
        ]
        n_out = int(self.head.get_output_details()[0]["shape"][-1])
        if n_out != len(self.labels):
            raise ModelError(f"the head has {n_out} outputs but {len(self.labels)} labels")

    def scores(self, windows: npt.NDArray[np.float32]) -> Scores:
        features = self._run(self.embedding, self.embedding_in, self.embedding_out, windows)
        if features.shape[-1] != self.width:
            raise ModelError(
                f"the embedding has {features.shape[-1]} values but the head expects {self.width}"
            )
        logits = self._run(self.head, self.head_in, self.head_out, features)
        # BattyBirdNET's own activation, at its default sensitivity.
        return np.asarray(1.0 / (1.0 + np.exp(-np.clip(logits, -15, 15))), dtype=np.float32)

    @staticmethod
    def _run(interpreter: Any, index_in: int, index_out: int, data: Any) -> Any:
        interpreter.resize_tensor_input(index_in, list(data.shape))
        interpreter.allocate_tensors()
        interpreter.set_tensor(index_in, data.astype(np.float32))
        interpreter.invoke()
        return interpreter.get_tensor(index_out)


def _window_leader(row: Scores, labels: Sequence[str], head: Head) -> Candidate | None:
    bats = [
        (float(s), head.bats[label])
        for label, s in zip(labels, row, strict=True)
        if label in head.bats
    ]
    if not bats:
        return None
    score, taxa = max(bats, key=lambda b: b[0])
    return Candidate(taxa=taxa, score=score)


def _download(url: str, target: Path, name: str, progress: Progress | None) -> None:
    with urllib.request.urlopen(url, timeout=60) as response, target.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(1 << 16):
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(name, done, total)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()
