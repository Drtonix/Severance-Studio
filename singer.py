"""Синтез пения из пиано-ролла: ноты + текст → вокал (DiffSinger ONNX, OpenUtau-формат банков).

Пайплайн (порт OpenUtau DiffSinger renderer):
  текст → G2P (русские правила) → фонемы по нотам
  dsdur:  linguistic.onnx + dur.onnx   → длительности фонем
  dsvariance: linguistic + variance    → breathiness/voicing/tension
  dsmain: acoustic.onnx                → mel
  dsvocoder: *.onnx                    → waveform
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import onnxruntime as ort
import soundfile as sf
import yaml

from g2p_gts import GTS_MAP, GTS_VOWELS, map_phones

SAMPLE_RATE = 44100
HOP = 512
FRAME_SEC = HOP / SAMPLE_RATE
HEAD_FRAMES = 8
TAIL_FRAMES = 8

# ---------------------------------------------------------------- русский G2P

_VOWELS_RU = "аеёиоуыэюя"
_CONS_SOFT = {
    "б": "bj", "в": "vj", "г": "gj", "д": "dj", "з": "zj", "к": "kj",
    "л": "lj", "м": "mj", "н": "nj", "п": "pj", "р": "rj", "с": "sj",
    "т": "tj", "ф": "fj", "х": "hj",
}
_CONS_HARD = {
    "б": "b", "в": "v", "г": "g", "д": "d", "ж": "zh", "з": "z",
    "й": "j", "к": "k", "л": "l", "м": "m", "н": "n", "п": "p",
    "р": "r", "с": "s", "т": "t", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "shj",
}
_FINAL_DEVOICE = {"б": "п", "в": "ф", "г": "к", "д": "т", "з": "с", "ж": "ш"}
_HARD_ONLY = set("жшц")  # никогда не смягчаются


def _iotated(letter: str, stressed: bool, after_soft: bool):
    """Е Ё Ю Я: j-форма (начало слова/после гласной/ъь) или смягчение + гласная."""
    if letter == "е":
        v = "e" if stressed else "i"
        return (["j", v] if after_soft is None else None, v)
    if letter == "ё":
        return (["j", "o"] if after_soft is None else None, "o")
    if letter == "ю":
        return (["j", "u"] if after_soft is None else None, "u")
    if letter == "я":
        v = "a" if stressed else "i"
        return (["j", v] if after_soft is None else None, v)
    return (None, None)


def g2p_ru_word(word: str) -> list[list[str]]:
    """Слово → список слогов, слог = список фонем ru/... .

    Ударение: ́ (U+0301) или ' после ударной гласной. Без метки ударным
    считается единственный слог; иначе все гласные — безударные варианты.
    """
    w = word.lower().replace("ё", "ё")
    stress_idx = None  # индекс гласной (в последовательности гласных) с ударением
    # найти метку ударения
    for m in re.finditer(r"([аеёиоуыэюя])[́']", w):
        stress_idx = len(re.findall(r"[аеёиоуыэюя]", w[: m.start()]))
        break
    w = w.replace("́", "").replace("'", "")
    # частные правила
    w = re.sub(r"ться\b", "цьа", w)
    w = re.sub(r"тся\b", "ца", w)
    if len(w) > 3 and (w.endswith("его") or w.endswith("ого")):
        w = w[:-3] + ("ево" if w.endswith("его") else "ово")
    vowel_total = len(re.findall(r"[аеёиоуыэюя]", w))
    if stress_idx is None and vowel_total == 1:
        stress_idx = 0

    letters = list(w)
    n = len(letters)
    phones: list[tuple[str, bool]] = []  # (фонема, is_vowel)
    prev_soft_req = False  # предыдущая согласная уже обработана как мягкая
    vowel_i = -1
    for i, ch in enumerate(letters):
        if ch in "ъь":
            continue  # смягчение обрабатывается взглядом вперёд
        if ch in _VOWELS_RU:
            vowel_i += 1
            stressed = (vowel_i == stress_idx) or (ch == "ё")
            # решить мягкость предыдущей согласной
            if phones and not phones[-1][1] and letters[i - 1] not in "ъь":
                pass
            prev_letter = letters[i - 1] if i > 0 else None
            prev_is_cons = prev_letter in _CONS_HARD
            after_soft = letters[i - 1] in "ьъ" if i > 0 else False
            standalone = (i == 0) or (prev_letter in _VOWELS_RU) or after_soft
            if ch in "еёюя":
                jform, vowel = _iotated(ch, stressed, None if standalone else "soft")
                if prev_is_cons and prev_letter in _CONS_SOFT and prev_letter not in _HARD_ONLY:
                    # заменить последнюю согласную на мягкую
                    phones[-1] = (_CONS_SOFT[prev_letter], False)
                    if ch in "ея" and not stressed and ch != "ё":
                        vowel = "i"
                    phones.append((vowel, True))
                elif prev_is_cons:
                    phones.append((vowel, True))
                else:
                    phones.extend([(p, k == 1) for k, p in enumerate(jform)])
                continue
            # простые гласные
            if ch == "и":
                if prev_is_cons and prev_letter in _CONS_SOFT and prev_letter not in _HARD_ONLY:
                    phones[-1] = (_CONS_SOFT[prev_letter], False)
                phones.append(("i", True))
                continue
            if ch == "а":
                phones.append(("A" if stressed else "a", True))
            elif ch == "о":
                phones.append(("o" if stressed else "a", True))
            elif ch == "э":
                phones.append(("E" if stressed else "i", True))
            elif ch == "ы":
                phones.append(("Y" if stressed else "y", True))
            elif ch == "у":
                phones.append(("u", True))
            continue
        if ch in _CONS_HARD:
            # оглушение в конце слова
            nxt = letters[i + 1] if i + 1 < n else None
            if nxt is None or nxt not in _VOWELS_RU + "йьъ" + "".join(_CONS_HARD):
                ch = _FINAL_DEVOICE.get(ch, ch)
            # мягкость по следующей букве (ь, е, ё, ю, я, и)
            soft_next = (nxt or "") in "ьеёюяи" and ch not in _HARD_ONLY
            if soft_next and ch in _CONS_SOFT:
                # мягкость применится при обработке гласной; здесь ставим мягкую сразу для "ь"
                if nxt == "ь":
                    phones.append((_CONS_SOFT[ch], False))
                else:
                    phones.append((_CONS_HARD[ch], False))
            else:
                phones.append((_CONS_HARD[ch], False))
            continue
        # прочие символы игнорируем
    if not phones:
        return []
    # оглушение: финальная звонкая (уже заменена выше по букве); рр → rr
    # делим на слоги: все согласные между гласными уходят в следующий слог
    syllables: list[list[str]] = []
    cur: list[str] = []
    seen_vowel = False
    for ph, is_v in phones:
        if is_v:
            cur.append(ph)
            syllables.append(cur)
            cur = []
            seen_vowel = True
        else:
            if not seen_vowel and not syllables:
                cur.append(ph)  # начальные согласные — в первый слог
            else:
                cur.append(ph)
    if cur:
        if syllables:
            syllables[-1].extend(cur)
        else:
            syllables.append(cur)
    return [["ru/" + p for p in syl] for syl in syllables]


RU_VOWELS = {f"ru/{v}" for v in ("a", "A", "e", "E", "i", "o", "u", "y", "Y")}


def lyrics_to_syllables(text: str) -> list[tuple[str, list[str]]]:
    """Текст → [(слог-отображение, [фонемы])] по слогам всех слов."""
    out = []
    for word in re.findall(r"[А-Яа-яЁёA-Za-ź']+", text):
        if re.search(r"[аеёиоуыэюя]", word.lower()):
            for syl in g2p_ru_word(word):
                out.append((word, syl))
        else:
            phones = ["ru/" + _CONS_HARD[c] for c in word.lower() if c in _CONS_HARD]
            if phones:
                out.append((word, phones))
    return out


# ---------------------------------------------------------------- модель

def _sess(path: Path) -> ort.InferenceSession:
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), sess_options=so,
                                providers=["CPUExecutionProvider"])


def _load_ids(path: Path) -> dict:
    return {k: int(v) for k, v in json.loads(path.read_text(encoding="utf8")).items()}


@dataclass
class SingNote:
    pitch: int          # MIDI
    start: float        # секунды
    dur: float          # секунды
    syllable: str = ""  # текст слога (или '+' для протяжения)


class DiffSingerBank:
    """Вокал-банк формата OpenUtau DiffSinger (dsmain/dsdur/dsvariance/dsvocoder)."""

    def __init__(self, bank_dir: str | Path, speaker: str = "Standard"):
        self.root = Path(bank_dir)
        cfg = yaml.safe_load((self.root / "dsconfig.yaml").read_text(encoding="utf8"))
        self.cfg = cfg
        self.hidden = cfg.get("hidden_size", 384)
        self.main_dir = self.root / cfg["acoustic"].rsplit("/", 1)[0] if "/" in cfg["acoustic"] else self.root
        self.main_phonemes = _load_ids(self.root / cfg["phonemes"])
        # авто-определение фонемного набора: банк на GTSinger-фонемах?
        self.gts_phonemes = ("a_ru" in self.main_phonemes
                             and "ru/a" not in self.main_phonemes)
        self.vowels = GTS_VOWELS if self.gts_phonemes else RU_VOWELS
        self.lang_ids = _load_ids(self.root / cfg["languages"]) if cfg.get("use_lang_id") else {}
        self.acoustic = _sess(self.root / cfg["acoustic"])
        # спикер эмбеддинг акустики
        spk_path = None
        for sp in cfg.get("speakers", []):
            if Path(sp).stem.lower() == speaker.lower():
                spk_path = self.root / (sp + ".emb")
                break
        if spk_path is None and cfg.get("speakers"):
            spk_path = self.root / (cfg["speakers"][0] + ".emb")
        self.spk_main = np.fromfile(spk_path, dtype=np.float32) if spk_path else None

        # dsdur
        self.dur_dir = self.root / "dsdur"
        dcfg = yaml.safe_load((self.dur_dir / "dsconfig.yaml").read_text(encoding="utf8"))
        self.dur_phonemes = _load_ids(self.dur_dir / dcfg["phonemes"])
        self.dur_linguistic = _sess(self.dur_dir / dcfg["linguistic"])
        self.dur_model = _sess(self.dur_dir / dcfg["dur"])
        self.dur_hidden = dcfg.get("hidden_size", 256)
        dspk = None
        for sp in dcfg.get("speakers", []):
            if Path(sp).stem.lower() == speaker.lower():
                dspk = self.dur_dir / (sp + ".emb")
                break
        if dspk is None and dcfg.get("speakers"):
            dspk = self.dur_dir / (dcfg["speakers"][0] + ".emb")
        self.spk_dur = np.fromfile(dspk, dtype=np.float32) if dspk else None

        # dsvariance (опционально)
        self.var_dir = self.root / "dsvariance"
        self.has_variance = self.var_dir.is_dir()
        if self.has_variance:
            vcfg = yaml.safe_load((self.var_dir / "dsconfig.yaml").read_text(encoding="utf8"))
            self.vcfg = vcfg
            self.var_phonemes = _load_ids(self.var_dir / vcfg["phonemes"])
            self.var_linguistic = _sess(self.var_dir / vcfg["linguistic"])
            self.var_model = _sess(self.var_dir / vcfg["variance"])
            self.var_hidden = vcfg.get("hidden_size", 256)
            vspk = None
            for sp in vcfg.get("speakers", []):
                if Path(sp).stem.lower() == speaker.lower():
                    vspk = self.var_dir / (sp + ".emb")
                    break
            if vspk is None and vcfg.get("speakers"):
                vspk = self.var_dir / (vcfg["speakers"][0] + ".emb")
            self.spk_var = np.fromfile(vspk, dtype=np.float32) if vspk else None

        # вокодер
        voc_dir = self.root / "dsvocoder"
        voc_cfg = yaml.safe_load((voc_dir / "vocoder.yaml").read_text(encoding="utf8"))
        self.vocoder = _sess(voc_dir / voc_cfg["model"])

    def _tokens(self, names: list[str], table: dict) -> np.ndarray:
        unk = table.get("SP", 2)
        return np.array([[table.get(p, unk) for p in names]], dtype=np.int64)

    def _langs(self, names: list[str]) -> np.ndarray:
        return np.array([[self.lang_ids.get(p.split("/")[0] if "/" in p else "", 0)
                          for p in names]], dtype=np.int64)

    # ------------------------------------------------ длительности
    def predict_durations(self, groups: list[list[str]], midis: list[int],
                          group_dur_frames: list[int]) -> list[float]:
        """groups: фонемы по слогам (группа 0 = SP + ведущие согласные),
        group_dur_frames: длительность каждой группы в кадрах (word_dur).
        Возвращает предсказанные длительности фонем (в кадрах, float)."""
        tokens = [p for g in groups for p in g]
        word_div = np.array([[len(g) for g in groups]], dtype=np.int64)
        word_dur = np.array([group_dur_frames], dtype=np.int64)
        ph_midi = np.array([[m for m, g in zip(midis, groups) for _ in g]], dtype=np.int64)
        inp = {
            "tokens": self._tokens(tokens, self.dur_phonemes),
            "languages": self._langs(tokens),
            "word_div": word_div,
            "word_dur": word_dur,
        }
        enc, x_masks = self.dur_linguistic.run(["encoder_out", "x_masks"], inp)
        dinp = {
            "encoder_out": enc,
            "x_masks": x_masks,
            "ph_midi": ph_midi,
            "word_div": word_div,
            "word_dur": word_dur,
        }
        if self.spk_dur is not None:
            dinp["spk_embed"] = np.tile(self.spk_dur, (1, len(tokens), 1)).astype(np.float32)
        ph_dur = self.dur_model.run(["ph_dur_pred"], dinp)[0][0]
        return ph_dur

    # ------------------------------------------------ варианты
    def predict_variance(self, tokens_names: list[str], ph_dur_frames: list[int],
                         pitch_frames: np.ndarray, steps: int = 10) -> dict:
        total = pitch_frames.shape[0]
        enc, x_masks = self.var_linguistic.run(
            ["encoder_out", "x_masks"],
            {"tokens": self._tokens(tokens_names, self.var_phonemes),
             "languages": self._langs(tokens_names),
             "ph_dur": np.array([ph_dur_frames], dtype=np.int64)})
        inp = {
            "encoder_out": enc,
            "ph_dur": np.array([ph_dur_frames], dtype=np.int64),
            "pitch": pitch_frames[None].astype(np.float32),
            "breathiness": np.zeros((1, total), np.float32),
            "voicing": np.zeros((1, total), np.float32),
            "tension": np.zeros((1, total), np.float32),
            "retake": np.ones((1, total, 3), bool),
            "steps": np.array([steps], np.int64),
        }
        if self.spk_var is not None:
            inp["spk_embed"] = np.tile(self.spk_var, (1, total, 1)).astype(np.float32)
        outs = self.var_model.run(["breathiness_pred", "voicing_pred", "tension_pred"], inp)
        return {"breathiness": outs[0][0], "voicing": outs[1][0], "tension": outs[2][0]}

    # ------------------------------------------------ акустика + вокодер
    def render(self, tokens_names: list[str], ph_dur_frames: list[int],
               f0: np.ndarray, variance: dict | None = None,
               steps: int = 20, gender: float = 0.0) -> np.ndarray:
        total = len(f0)
        inp = {
            "tokens": self._tokens(tokens_names, self.main_phonemes),
            "languages": self._langs(tokens_names),
            "durations": np.array([ph_dur_frames], dtype=np.int64),
            "f0": f0[None].astype(np.float32),
            "gender": np.full((1, total), gender, np.float32),
            "velocity": np.ones((1, total), np.float32),
            "steps": np.array([steps], np.int64),
        }
        if variance is not None:
            inp["breathiness"] = np.clip(variance["breathiness"], -96, 0)[None].astype(np.float32)
            inp["voicing"] = np.clip(variance["voicing"], -96, 0)[None].astype(np.float32)
            inp["tension"] = np.clip(variance["tension"], -10, 10)[None].astype(np.float32)
        else:
            z = np.zeros((1, total), np.float32)
            inp.update({"breathiness": z, "voicing": z, "tension": z})
        if self.spk_main is not None:
            inp["spk_embed"] = np.tile(self.spk_main, (1, total, 1)).astype(np.float32)
        mel = self.acoustic.run(["mel"], inp)[0]
        wav = self.vocoder.run(["waveform"], {"mel": mel, "f0": f0[None].astype(np.float32)})[0][0]
        return wav

    # ------------------------------------------------ полный синтез
    def sing(self, notes: list[SingNote], out_wav: str | Path | None = None,
             steps: int = 20, variance_steps: int = 10,
             speaker: str | None = None) -> np.ndarray:
        if speaker and speaker.lower() != "standard":
            self.__init__(self.root, speaker)  # простая перезагрузка эмбеддингов
        # 1. слоги по нотам
        syll_phones: list[list[str]] = []
        last_vowel = "ru/a"
        for nt in notes:
            syl = nt.syllable.strip()
            if syl in ("+", "", None):
                syll_phones.append([last_vowel])
            else:
                parsed = lyrics_to_syllables(syl)
                if not parsed:
                    ph = [last_vowel]
                elif len(parsed) == 1:
                    ph = parsed[0][1]
                else:
                    # несколько слогов на одной ноте: склеиваем фонемы в одну группу
                    ph = [p for _, s in parsed for p in s]
                syll_phones.append(ph)
                for p in ph:
                    if p in RU_VOWELS:
                        last_vowel = p
        if self.gts_phonemes:
            syll_phones = [map_phones(ph) for ph in syll_phones]
            last_vowel = GTS_MAP.get(last_vowel, last_vowel)
        # 2. группы: [SP+нач.согласные], по группе на ноту, граница в конце
        groups: list[list[str]] = []
        g_midis: list[int] = []
        g_dur_frames: list[int] = []
        first = syll_phones[0]
        pre = [p for p in first if p not in self.vowels]
        first_vi = next((i for i, p in enumerate(first) if p in self.vowels), len(first))
        groups.append(["SP"] + first[:first_vi])
        g_midis.append(notes[0].pitch)
        # длительность группы 0: 500 мс паддинг
        g_dur_frames.append(round(0.5 / FRAME_SEC))
        # остальные: ведущие согласные ноты k (после первой) добавляем в её группу;
        # слог без гласной целиком — группа из согласных
        rest0 = first[first_vi:]
        syll_phones[0] = rest0
        prev_end = None
        for i, (nt, ph) in enumerate(zip(notes, syll_phones)):
            if prev_end is not None and nt.start > prev_end + 0.02:
                # пауза между нотами — SP-группа
                groups.append(["SP"])
                g_midis.append(nt.pitch)
                g_dur_frames.append(max(round((nt.start - prev_end) / FRAME_SEC), 1))
            groups.append(ph)
            g_midis.append(nt.pitch)
            g_dur_frames.append(round(nt.dur / FRAME_SEC))
            prev_end = nt.start + nt.dur
        g_dur_frames[-1] = max(g_dur_frames[-1], 1)
        # 3. предсказание длительностей (в кадрах)
        pred = self.predict_durations(groups, g_midis, g_dur_frames)
        # 4. выравнивание: каждую группу масштабируем под её бюджет кадров
        aligned: list[float] = []
        off = 0
        for g, budget in zip(groups, g_dur_frames):
            seg = pred[off:off + len(g)]
            off += len(g)
            s = float(seg.sum())
            if s <= 0:
                seg = np.full(len(g), budget / max(len(g), 1))
            else:
                seg = seg * (budget / s)
            aligned.extend(seg.tolist())
        # группа 0: SP играет роль ведущей паузы; обрежем её до 8 кадров,
        # а согласные оставим перед первой нотой (как в OpenUtau, leading)
        # преобразуем в кадры с кумулятивным округлением
        acc = np.cumsum(aligned) / 1.0
        frames = np.diff(np.round(acc + 0.5).astype(np.int64), prepend=0).tolist()
        # 5. итоговые последовательности с head/tail SP
        lead_frames = frames[:len(groups[0])]  # SP + ведущие согласные
        body_tokens = [p for g in groups[1:] for p in g]
        body_frames = frames[len(groups[0]):]
        tokens = ["SP"] + body_tokens + ["SP"]
        # ведущие согласные идут ДО первой ноты: включаем их в вывод
        lead_cons = groups[0][1:]
        lead_cons_frames = lead_frames[1:]
        tokens = ["SP"] + lead_cons + body_tokens + ["SP"]
        ph_frames = [HEAD_FRAMES] + lead_cons_frames + body_frames + [TAIL_FRAMES]
        total = sum(ph_frames)
        # 6. f0 и pitch по кадрам
        note_of_frame = np.zeros(total, np.float32)  # midi pitch
        f0 = np.zeros(total, np.float32)
        pos = 0.0
        t0 = notes[0].start - (HEAD_FRAMES + sum(lead_cons_frames)) * FRAME_SEC
        edges = [(nt.start, nt.start + nt.dur, nt.pitch) for nt in notes]
        for i in range(total):
            t = t0 + i * FRAME_SEC
            pitch = edges[0][2]
            for s, e, p in edges:
                if t >= s - sum(lead_cons_frames) * FRAME_SEC - 1e-9 and t < e:
                    pitch = p
                    break
            else:
                if t >= edges[-1][1]:
                    pitch = edges[-1][2]
                else:
                    # в разрыве — ближайшая следующая нота
                    for s, e, p in edges:
                        if t < s:
                            pitch = p
                            break
            note_of_frame[i] = pitch
            f0[i] = 440.0 * 2 ** ((pitch - 69) / 12)
        # 7. варианты
        variance = None
        if self.has_variance:
            variance = self.predict_variance(tokens, ph_frames, note_of_frame, steps=variance_steps)
        # 8. акустика + вокодер
        wav = self.render(tokens, ph_frames, f0, variance=variance, steps=steps)
        # обрезаем только хвостовой SP; head SP (8 кадров) оставляем как тишину перед ведущими согласными
        wav = wav[: (total - TAIL_FRAMES) * HOP]
        if out_wav:
            sf.write(str(out_wav), wav, SAMPLE_RATE)
        return wav


def notes_from_pianoroll(notes, text: str) -> list[SingNote]:
    """notes: список engine.Note (pitch/start/dur) или dict'ов; text — слова по слогам."""
    syls = [w for w in re.split(r"\s+", text.strip()) if w]
    out = []
    si = 0
    for n in notes:
        pitch = n["pitch"] if isinstance(n, dict) else n.pitch
        start = n["start"] if isinstance(n, dict) else n.start
        dur = n["dur"] if isinstance(n, dict) else n.dur
        syl = "+"
        if si < len(syls):
            syl = syls[si]
            si += 1
        out.append(SingNote(pitch=int(pitch), start=float(start), dur=float(dur), syllable=syl))
    return out


if __name__ == "__main__":
    import sys

    bank = Path(__file__).parent / "models" / "nishiren" / "Nishiren Diffsinger v2.1"
    singer = DiffSingerBank(bank)
    # тест: «Во поле берёза стояла» на простой мелодии
    text = "Во по ле бе рё за сто я ла"
    melody = [62, 62, 64, 65, 64, 62, 60, 62, 60]
    durs = [0.5] * 9
    notes = []
    t = 0.0
    for p, d, s in zip(melody, durs, text.split()):
        notes.append(SingNote(pitch=p, start=t, dur=d, syllable=s))
        t += d
    out = Path(__file__).parent / "output" / "sing_test.wav"
    out.parent.mkdir(exist_ok=True)
    wav = singer.sing(notes, out)
    print("OK", out, len(wav) / SAMPLE_RATE, "s")
