"""Движок Severance Studio: стемы → ноты → MIDI → Ableton, голоса по промпту.

Слой над моделями. Интерфейсы стабильны, реализация подключается поэтапно:
1) stems()        — разбор на дорожки (demucs-mlx / mlx-audio-separator)
2) transcribe()   — дорожка → ноты (Basic Pitch, CoreML)
3) export_live()  — стемы + MIDI + темп → проект Ableton (.als)
4) design_voice() — промпт → образец голоса (Qwen3-TTS VoiceDesign)
5) sing()         — мелодия + текст + голос → вокальная дорожка (Seed-VC)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Те же модели, что в Severance: четыре дорожки demucs для скорости,
# BS-RoFormer для чистого голоса/музыки.
FAST_MODEL = "htdemucs_ft"

STEMS = ("vocals", "drums", "bass", "guitar", "piano", "other")


@dataclass
class Note:
    start: float          # секунды
    duration: float
    pitch: int            # MIDI 0..127
    velocity: int = 100


@dataclass
class Track:
    """Одна дорожка проекта: стем и его пиано-ролл."""
    stem: str
    audio: Path | None = None
    notes: list[Note] = field(default_factory=list)


@dataclass
class Project:
    name: str
    source: Path
    bpm: float = 0.0
    key: str = ""
    tracks: list[Track] = field(default_factory=list)


# ---------------------------------------------------------------- стемы

def stems(wav: Path, out: Path, progress=None) -> dict[str, Path]:
    """Разбор на дорожки через demucs-mlx (как separate_fast в Severance)."""
    from demucs_mlx.api import Separator

    out.mkdir(parents=True, exist_ok=True)
    with Separator(model=FAST_MODEL) as sep:
        paths = sep.separate(str(wav), output_dir=str(out),
                             filename_format="{stem}.wav")
    return {k: Path(v) for k, v in paths.items()}


# ---------------------------------------------------------------- ноты

def transcribe(stem_audio: Path, progress=None) -> list[Note]:
    """Дорожка → список нот. Basic Pitch на CoreML: мелодика и бас.
    Ударные транскрибируются отдельным проходом (см. transcribe_drums)."""
    from basic_pitch.inference import predict

    _, midi_data, _ = predict(str(stem_audio))
    notes = [
        Note(start=n.start,
             duration=n.end - n.start,
             pitch=n.pitch,
             velocity=n.velocity)
        for inst in midi_data.instruments
        for n in inst.notes
    ]
    notes.sort(key=lambda n: n.start)
    return notes


def transcribe_drums(stem_audio: Path, progress=None) -> list[Note]:
    """Ударные → ноты GM (36 kick, 38 snare, 42/46 hat...). Этап 2."""
    raise NotImplementedError("транскрипция ударных — этап 2")


# ---------------------------------------------------------------- MIDI

def to_midi(track: Track, out: Path, bpm: float) -> Path:
    """Пиано-ролл дорожки → стандартный .mid для Ableton."""
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(initial_tempo=bpm or 120)
    inst = pretty_midi.Instrument(
        program=0, is_drum=(track.stem == "drums"), name=track.stem)
    for n in track.notes:
        inst.notes.append(pretty_midi.Note(
            velocity=n.velocity, pitch=n.pitch,
            start=n.start, end=n.start + n.duration))
    midi.instruments.append(inst)
    midi.write(str(out))
    return out


# ---------------------------------------------------------------- Ableton

def export_live(project: Project, out_dir: Path, progress=None) -> Path:
    """Стемы + MIDI + темп-карта → .als (gzip+XML). Этап 3.
    Пока: экспорт папки со стемами и .mid — Ableton принимает drag-and-drop."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for track in project.tracks:
        if track.notes:
            to_midi(track, out_dir / f"{track.stem}.mid", project.bpm)
    return out_dir


# ---------------------------------------------------------------- голоса

def design_voice(prompt: str, lang: str, out: Path, progress=None) -> Path:
    """Текстовый промпт ('роботичная девочка, высокий голос') → образец
    голоса через Qwen3-TTS VoiceDesign. Образец — эталон тембра. Этап 4."""
    raise NotImplementedError("голоса по промпту — этап 4")


def sing(melody: list[Note], lyrics: str, voice_ref: Path,
         out: Path, progress=None) -> Path:
    """Мелодия + текст + эталон тембра → спетая дорожка (Seed-VC). Этап 4."""
    raise NotImplementedError("синтез пения — этап 4")
