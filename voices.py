"""Голосовая лаборатория Severance Studio.

Вокалоид создаётся текстовым промптом — петь самому не нужно:
1. design_voice()  промпт → Qwen3-TTS VoiceDesign → образцы голоса (тембр)
2. convert_voice() Seed-VC перекрашивает пение трека в тембр вокалоида
   (отдельный процесс: Seed-VC держит numpy<2 и GPL-3.0)

Библиотека голосов — voices/<имя>/: meta.json + эталонные wav.
Добавление своего голоса = новая папка с meta.json и wav-эталоном.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

DESIGN_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"
SR = 24000

VOICES_HOME = Path(__file__).parent / "voices"

# Окружение Seed-VC: в разработке делим с Severance, в бандле будет своё
SEVERANCE_VOICE = Path("/Users/tonix/Developer/severance/voice")

# Фразы-образцы: важно покрыть гласные и певучие слоги
SAMPLE_LINES = {
    "Russian": [
        "Моя мелодия летит над городом, ла-ла-ла, ла-ла-ла.",
        "Я пою тебе о звёздах, о луне, о тёплом лете.",
        "Раз, два, три — проверка голоса, ми-ми-ми, ма-ма-ма.",
    ],
    "English": [
        "My melody is flying over the city, la-la-la, la-la-la.",
        "I sing to you about stars, about the moon, about summer.",
        "One, two, three — testing my voice, mee-mee-mee, ma-ma-ma.",
    ],
}
LANG_NAMES = {"ru": "Russian", "en": "English"}


@dataclass
class Voice:
    vid: str
    name: str
    prompt: str
    lang: str
    refs: list[Path]
    created: float


def _slug(name: str) -> str:
    s = re.sub(r"[^\wа-яА-ЯёЁ-]+", "-", name.strip().lower()).strip("-")
    return s or "voice"


def list_voices() -> list[Voice]:
    out = []
    if not VOICES_HOME.exists():
        return out
    for d in sorted(VOICES_HOME.iterdir()):
        meta = d / "meta.json"
        if not meta.exists():
            continue
        m = json.loads(meta.read_text())
        refs = sorted(d.glob("ref_*.wav"))
        if refs:
            out.append(Voice(d.name, m["name"], m["prompt"],
                             m.get("lang", "ru"), refs, m.get("created", 0)))
    return out


def get_voice(vid: str) -> Voice | None:
    return next((v for v in list_voices() if v.vid == vid), None)


# ---------------------------------------------------------------- дизайн

def _load_design():
    from mlx_audio.tts.utils import load_model
    return load_model(DESIGN_MODEL)


def _collect(gen) -> "object":
    import numpy as np
    chunks = [np.asarray(g.audio, dtype=np.float32).reshape(-1) for g in gen]
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def design_voice(name: str, prompt: str, lang: str = "ru",
                 progress=None) -> Voice:
    """Промпт ('высокий синтетический голос девочки-робота') → вокалоид."""
    import numpy as np
    import soundfile as sf

    vid = _slug(name)
    vdir = VOICES_HOME / vid
    vdir.mkdir(parents=True, exist_ok=True)

    if progress:
        progress("Загрузка VoiceDesign…")
    model = _load_design()

    language = LANG_NAMES.get(lang, "Russian")
    lines = SAMPLE_LINES.get(language, SAMPLE_LINES["Russian"])
    refs: list[Path] = []
    for i, line in enumerate(lines, 1):
        if progress:
            progress(f"Образец {i}/{len(lines)}: «{line[:40]}…»")
        audio = _collect(model.generate_voice_design(
            text=line, instruct=prompt, language=language))
        ref = vdir / f"ref_{i}.wav"
        sf.write(str(ref), audio, SR)
        refs.append(ref)

    meta = {"name": name, "prompt": prompt, "lang": lang,
            "created": time.time()}
    (vdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False,
                                               indent=2))
    return Voice(vid, name, prompt, lang, refs, meta["created"])


# ---------------------------------------------------------------- конверсия

def _voice_python() -> Path | None:
    for p in (Path(__file__).parent / "voice" / ".venv" / "bin" / "python",
              SEVERANCE_VOICE / ".venv" / "bin" / "python"):
        if p.exists():
            return p
    return None


def _convert_script() -> Path:
    own = Path(__file__).parent / "voice" / "convert.py"
    return own if own.exists() else SEVERANCE_VOICE / "convert.py"


def convert_voice(source: Path, voice: Voice, out: Path, *,
                  steps: int = 30, shift: int = 0, progress=None) -> Path:
    """Пение source → тембр вокалоида. shift — сдвиг тона в полутонах."""
    py = _voice_python()
    if not py:
        raise RuntimeError("окружение смены голоса не найдено "
                           "(voice/.venv или Severance/voice/.venv)")
    ref = max(voice.refs, key=lambda p: p.stat().st_size)
    cmd = [str(py), str(_convert_script()), str(source), str(ref), str(out),
           "--steps", str(steps)]
    if shift:
        cmd += ["--shift", str(shift)]
    env = dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK="1")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env)
    for line in proc.stdout:
        if progress and line.strip():
            progress(line.strip())
    proc.wait()
    if proc.returncode != 0 or not out.exists():
        err = proc.stderr.read().strip().splitlines()
        raise RuntimeError(err[-1] if err else "смена голоса не удалась")
    return out
