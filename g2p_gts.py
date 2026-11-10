"""Маппинг внутренних фонем нашего русского G2P (ru/...) на фонемный
набор GTSinger (a_ru, n̪_ru, …), на котором обучаются свои банки
(GTSinger RU-Alto-1, датасет openvpi_ru).

Авто-определение в singer.DiffSingerBank: если в таблице фонем банка
есть «a_ru» и нет «ru/a» — маппинг включается сам.
"""

# ru/X (наш G2P) → токен GTSinger
GTS_MAP = {
    # гласные
    "ru/a": "ɐ_ru",   # безударные а/о → редуцированная
    "ru/A": "a_ru",   # ударная а
    "ru/e": "e_ru",   # ударная е
    "ru/E": "ɛ_ru",   # ударная э
    "ru/i": "i_ru",   # и / безударные е, э, я
    "ru/o": "o_ru",   # ударная о
    "ru/u": "u_ru",   # у
    "ru/y": "ɨ_ru",   # безударная ы
    "ru/Y": "ɨ_ru",   # ударная ы
    # твёрдые согласные
    "ru/b": "b_ru",   "ru/v": "v_ru",   "ru/g": "ɡ_ru",
    "ru/d": "d̪_ru",   "ru/zh": "ʐ_ru",  "ru/z": "z̪_ru",
    "ru/j": "j_ru",   "ru/k": "k_ru",   "ru/l": "ɫ_ru",
    "ru/m": "m_ru",   "ru/n": "n̪_ru",   "ru/p": "p_ru",
    "ru/r": "r_ru",   "ru/s": "s̪_ru",   "ru/t": "t̪_ru",
    "ru/f": "f_ru",   "ru/h": "x_ru",   "ru/c": "t̪s̪_ru",
    "ru/ch": "tɕ_ru", "ru/sh": "ʂ_ru",  "ru/shj": "ɕː_ru",
    # мягкие согласные
    "ru/bj": "bʲ_ru", "ru/vj": "vʲ_ru", "ru/gj": "ɟ_ru",
    "ru/dj": "dʲ_ru", "ru/zj": "zʲ_ru", "ru/kj": "c_ru",
    "ru/lj": "ʎ_ru",  "ru/mj": "mʲ_ru", "ru/nj": "ɲ_ru",
    "ru/pj": "pʲ_ru", "ru/rj": "rʲ_ru", "ru/sj": "sʲ_ru",
    "ru/tj": "tsʲ_ru", "ru/fj": "fʲ_ru", "ru/hj": "ç_ru",
    # служебные
    "SP": "SP", "AP": "AP",
}

# гласные в наборе GTSinger (для поиска «опорной» гласной слога)
GTS_VOWELS = {
    "a_ru", "ə_ru", "ɐ_ru", "e_ru", "ɪ_ru", "i_ru", "o_ru", "u_ru",
    "ɨ_ru", "ʊ_ru", "ɛ_ru", "æ_ru", "ɵ_ru", "ʉ_ru",
}


def map_phones(phones: list[str]) -> list[str]:
    return [GTS_MAP.get(p, p) for p in phones]
