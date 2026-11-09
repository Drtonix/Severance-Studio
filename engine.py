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

def transcribe(stem_audio: Path, progress=None, *,
               onset: float = 0.6, frame: float = 0.4,
               min_len_ms: float = 90.0,
               min_pitch: int = 21, max_pitch: int = 108) -> list[Note]:
    """Дорожка → список нот. Basic Pitch на CoreML: мелодика и бас.
    Ударные транскрибируются отдельным проходом (см. transcribe_drums).

    onset/frame — пороги уверенности модели (выше = чище, но пропуски),
    min_len_ms — отсечка коротких шумовых нот."""
    from basic_pitch.inference import predict

    _, midi_data, _ = predict(
        str(stem_audio),
        onset_threshold=onset,
        frame_threshold=frame,
        minimum_note_length=min_len_ms,
    )
    notes = [
        Note(start=n.start,
             duration=n.end - n.start,
             pitch=n.pitch,
             velocity=n.velocity)
        for inst in midi_data.instruments
        for n in inst.notes
        if min_pitch <= n.pitch <= max_pitch
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


# ---------------------------------------------------------------- BPM

def detect_bpm(wav: Path, progress=None) -> float:
    """Темп через beat-this. Сбой модели → 120 как безопасный дефолт."""
    try:
        from beat_this.inference import File2Beats

        f2b = File2Beats()
        beats, _ = f2b(str(wav))
        import numpy as np

        intervals = np.diff(beats)
        if len(intervals) < 4:
            return 120.0
        bpm = 60.0 / float(np.median(intervals))
        while bpm < 70:
            bpm *= 2
        while bpm > 180:
            bpm /= 2
        return round(bpm, 1)
    except Exception:  # noqa: BLE001 — темп не критичен, есть дефолт
        return 120.0


# ---------------------------------------------------------------- Ableton

def export_live(project: Project, out_dir: Path, progress=None,
                open_live: bool = False) -> Path:
    """Стемы + MIDI + готовый .als с расставленными дорожками и темпом."""
    import shutil

    from als import write_als

    bpm = project.bpm or 120.0
    stems_dir = out_dir / "stems"
    midi_dir = out_dir / "midi"
    stems_dir.mkdir(parents=True, exist_ok=True)
    midi_dir.mkdir(parents=True, exist_ok=True)

    stem_files: dict[str, Path] = {}
    for track in project.tracks:
        if track.audio and track.audio.exists():
            dst = stems_dir / track.audio.name
            if track.audio.resolve() != dst.resolve():
                shutil.copy2(track.audio, dst)
            stem_files[track.stem] = dst
        if track.notes:
            to_midi(track, midi_dir / f"{track.stem}.mid", bpm)

    als_path = write_als(project, out_dir / f"{project.name}.als",
                         stem_files, bpm)
    if open_live:
        import subprocess

        subprocess.Popen(["open", str(als_path)])
    return als_path


# ---------------------------------------------------------------- превью

WAVEFORMS = ("sine", "triangle", "saw", "square")


def render_preview(notes: list[Note], out: Path, *,
                   waveform: str = "saw", sr: int = 44100) -> Path:
    """Ноты → wav для предпрослушки. Простой синтез с ADSR-огибающей:
    звук меняется параметром waveform, пиано-ролл остаётся тем же."""
    import numpy as np
    import soundfile as sf

    end = max((n.start + n.duration for n in notes), default=1.0) + 0.3
    mix = np.zeros(int(end * sr), dtype=np.float32)
    t_cache: dict[int, np.ndarray] = {}

    for n in notes:
        freq = 440.0 * 2 ** ((n.pitch - 69) / 12)
        N = max(1, int(n.duration * sr))
        if N not in t_cache:
            t_cache[N] = np.arange(N) / sr
        t = t_cache[N]
        ph = 2 * np.pi * freq * t
        if waveform == "sine":
            wave = np.sin(ph)
        elif waveform == "triangle":
            wave = 2 * np.abs(2 * ((freq * t) % 1) - 1) - 1
        elif waveform == "square":
            wave = np.sign(np.sin(ph))
        else:  # saw
            wave = 2 * ((freq * t) % 1) - 1
        # ADSR: короткая атака, линейный спад к концу ноты
        a = max(1, int(0.01 * sr))
        env = np.ones(N, dtype=np.float32)
        env[:a] = np.linspace(0, 1, a)
        env *= np.linspace(1, 0.6, N)
        amp = (n.velocity / 127) * 0.2
        i0 = int(n.start * sr)
        mix[i0:i0 + N] += (wave * env * amp).astype(np.float32)

    peak = np.max(np.abs(mix))
    if peak > 1e-6:
        mix *= 0.8 / peak          # нормализация до −2 дБ
    mix = np.tanh(mix * 1.4).astype(np.float32)  # мягкий лимитер от перегруза
    sf.write(str(out), mix, sr)
    return out


# ---------------------------------------------------------------- голоса

def design_voice(prompt: str, lang: str, out: Path, progress=None) -> Path:
    """Текстовый промпт ('роботичная девочка, высокий голос') → образец
    голоса через Qwen3-TTS VoiceDesign. Образец — эталон тембра. Этап 4."""
    raise NotImplementedError("голоса по промпту — этап 4")


def sing(melody: list[Note], lyrics: str, voice_ref: Path,
         out: Path, progress=None) -> Path:
    """Мелодия + текст + эталон тембра → спетая дорожка (Seed-VC). Этап 4."""
    raise NotImplementedError("синтез пения — этап 4")
