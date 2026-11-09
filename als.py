"""Генератор проекта Ableton Live (.als — gzip + XML).

Собирает минимальный валидный LiveSet: аудиодорожки со стемами,
MIDI-дорожки с клипами-нотами, темп в мастер-дорожке. Live 12
дозаполняет пропущенные необязательные поля значениями по умолчанию.
"""
from __future__ import annotations

import gzip
import html
import re
from pathlib import Path

from engine import Project, Track

XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'

# Цвета дорожек в палитре Live (индексы), чтобы стемы различались сразу
TRACK_COLORS = [16, 26, 40, 51, 63, 70, 8, 33]

_id = [100]


def nid() -> int:
    _id[0] += 1
    return _id[0]


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def follow_action() -> str:
    return ('<FollowAction><FollowTime Value="4"/><IsLinked Value="true"/>'
            '<TakeTrueChance Value="100"/><TakeFalseChance Value="0"/>'
            '<FollowActionA Value="0"/><FollowActionB Value="0"/>'
            '<FollowChanceA Value="100"/><FollowChanceB Value="0"/>'
            '<JumpIndexA Value="1"/><JumpIndexB Value="1"/>'
            '<FollowActionEnabled Value="false"/></FollowAction>')


def time_signature() -> str:
    return (f'<TimeSignature><TimeSignatures>'
            f'<RemoteableTimeSignature Id="{nid()}">'
            '<Numerator Value="4"/><Denominator Value="4"/><Time Value="0"/>'
            '</RemoteableTimeSignature></TimeSignatures></TimeSignature>')


def clip_common(name: str, end_beats: float, warped: bool) -> str:
    return (f'<LomId Value="0"/><LomIdView Value="0"/>'
            f'<CurrentStart Value="0"/><CurrentEnd Value="{end_beats:.6f}"/>'
            f'<Loop><LoopStart Value="0"/><LoopEnd Value="{end_beats:.6f}"/>'
            f'<StartRelative Value="0"/><LoopOn Value="false"/>'
            f'<OutMarker Value="{end_beats:.6f}"/>'
            f'<HiddenLoopStart Value="0"/><HiddenLoopEnd Value="{end_beats:.6f}"/></Loop>'
            f'<Name Value="{esc(name)}"/><Annotation Value=""/><Color Value="-1"/>'
            f'<LaunchMode Value="0"/><LaunchQuantisation Value="0"/>'
            + time_signature() +
            '<Envelopes><Envelopes/></Envelopes>'
            f'<ScrollerTimePreserver><LeftTime Value="0"/><RightTime Value="{end_beats:.6f}"/></ScrollerTimePreserver>'
            '<TimeSelection><AnchorTime Value="0"/><OtherTime Value="0"/></TimeSelection>'
            '<Legato Value="false"/><Ram Value="false"/>'
            '<GrooveSettings><GrooveId Value="-1"/></GrooveSettings>'
            '<Disabled Value="false"/><VelocityAmount Value="0"/>'
            + follow_action() +
            '<Grid><FixedNumerator Value="1"/><FixedDenominator Value="16"/>'
            '<GridIntervalPixel Value="20"/><Ntoles Value="2"/>'
            '<SnapToGrid Value="true"/><Fixed Value="false"/></Grid>'
            '<FreezeStart Value="0"/><FreezeEnd Value="0"/>'
            f'<IsWarped Value="{str(warped).lower()}"/><TakeId Value="0"/>')


def audio_clip(wav: Path, end_beats: float, bpm: float) -> str:
    import soundfile as sf

    st = wav.stat()
    dur_sec = sf.info(str(wav)).duration
    end_beat_warp = dur_sec * bpm / 60.0
    warp = (f'<WarpMarkers>'
            f'<WarpMarker Id="0" SecTime="0" BeatTime="0"/>'
            f'<WarpMarker Id="1" SecTime="{dur_sec:.6f}" BeatTime="{end_beat_warp:.6f}"/>'
            f'</WarpMarkers>')
    return (f'<AudioClip Id="{nid()}" Time="0">' + clip_common(wav.name, end_beats, False) +
            f'<SampleRef><FileRef>'
            f'<RelativePathType Value="3"/><RelativePath Value=""/>'
            f'<Path Value="{esc(str(wav.resolve()))}"/>'
            f'<Type Value="2"/><LivePackName Value=""/><LivePackId Value=""/>'
            f'<OriginalFileSize Value="{st.st_size}"/>'
            f'<OriginalCrc Value="{st.st_size % 100000}"/>'
            f'</FileRef><LastModDate Value="{int(st.st_mtime)}"/>'
            f'<SourceContext><SourceContext Id="0"><OriginalFileRef><FileRef Id="0">'
            f'<RelativePathType Value="0"/><RelativePath Value=""/><Path Value=""/>'
            f'<Type Value="0"/><LivePackName Value=""/><LivePackId Value=""/>'
            f'</FileRef></OriginalFileRef><BrowserContentPath Value=""/></SourceContext></SourceContext>'
            f'<SampleUsageHint Value="0"/></SampleRef>'
            f'<Onsets><UserOnsets/><HasUserOnsets Value="false"/></Onsets>'
            f'<WarpMode Value="0"/><GranularityTones Value="30"/>'
            f'<GranularityTexture Value="65"/><FluctuationTexture Value="25"/>'
            f'<TotalResolution Value="16"/><TransientResolution Value="6"/>'
            f'<TransientLoopMode Value="2"/><TransientEnvelope Value="100"/>'
            f'<ComplexProFormants Value="100"/><ComplexProEnvelope Value="128"/>'
            f'<Sync Value="false"/><HiQ Value="true"/><Fade Value="true"/>'
            f'<Fades><FadeInLength Value="60000"/><FadeOutLength Value="60000"/>'
            f'<ClipFadesAreInitialized Value="true"/><CrossfadeInState Value="0"/>'
            f'<FadeInHandleSkew Value="0"/><FadeOutHandleSkew Value="0"/>'
            f'<IsClipFadeInActive Value="true"/><IsClipFadeOutActive Value="true"/></Fades>'
            f'<PitchCoarse Value="0"/><PitchFine Value="0"/><SampleVolume Value="1"/>'
            f'<MarkerDensity Value="2"/><AutoWarpTolerance Value="4"/>'
            f'<SavedWarpMarkersForStretched/>' + warp +
            f'<IsSampleAliasFromBrowser Value="false"/><SampleModulations/>'
            f'</AudioClip>')


_note_counter = [0]


def midi_clip(track: Track, bpm: float) -> str:
    sec2beat = bpm / 60.0
    by_key: dict[int, list[str]] = {}
    for n in track.notes:
        _note_counter[0] += 1
        note_id = _note_counter[0]
        t = n.start * sec2beat
        d = max(0.05, n.duration * sec2beat)
        ev = (f'<MidiNoteEvent Time="{t:.6f}" Duration="{d:.6f}" '
              f'Velocity="{n.velocity}" VelocityDeviation="0" '
              f'OffVelocity="64" Probability="1" IsEnabled="true" NoteId="{note_id}"/>')
        by_key.setdefault(n.pitch, []).append(ev)
    keys = "".join(
        f'<KeyTrack Id="{nid()}"><Notes>{"".join(evs)}</Notes>'
        f'<MidiKey Value="{pitch}"/></KeyTrack>'
        for pitch, evs in sorted(by_key.items()))
    end_beats = max((n.start + n.duration) * sec2beat for n in track.notes) \
        if track.notes else 4.0
    return (f'<MidiClip Id="{nid()}" Time="0">' + clip_common(track.stem, end_beats, True) +
            f'<Notes><KeyTracks>{keys}</KeyTracks></Notes>'
            f'<BankSelectMsb Value="-1"/><BankSelectLsb Value="-1"/>'
            f'<BankSelectPc Value="-1"/></MidiClip>')


def _load_template() -> str:
    """Эталонный LiveSet: сначала из установленного Live, потом из репо."""
    import glob

    for app in sorted(glob.glob("/Applications/Ableton Live */Contents")):
        p = Path(app) / "App-Resources/Builtin/Templates/DefaultLiveSet.als"
        if p.exists():
            try:
                with gzip.open(p, "rt", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                return p.read_text(encoding="utf-8")
    return (Path(__file__).parent / "templates" / "DefaultLiveSet.xml") \
        .read_text(encoding="utf-8")


def _skeleton(xml: str, tag: str) -> str:
    m = re.search(r'\t\t\t<' + tag + r'[ >].*?\t\t\t</' + tag + '>', xml, re.S)
    if not m:
        raise ValueError(f"в шаблоне нет {tag}")
    return m.group(0)


def _clone_track(skeleton: str, name: str, color: int,
                 events_xml: str, kind: str) -> str:
    """Клон скелета дорожки: свежие Id, имя, цвет и клипы в аранжировке."""
    def fresh(m: re.Match) -> str:
        return f'{m.group(1)}"{nid()}"'

    out = re.sub(r'(Id=)"\d+"', fresh, skeleton)
    out = re.sub(r'(<EffectiveName Value=")[^"]*(")', rf'\g<1>{esc(name)}\g<2>',
                 out, count=1)
    out = re.sub(r'(<Color Value=")-?\d+(")', rf'\g<1>{color}\g<2>', out,
                 count=1)
    # первый <Events /> в MainSequencer — клипы аранжировки
    i = out.find("<MainSequencer>")
    j = out.find("<Events />", i)
    if j < 0:
        raise ValueError(f"в скелете {kind} нет Events аранжировки")
    out = out[:j] + f"<Events>{events_xml}</Events>" + out[j + len("<Events />"):]
    return out


def build_xml(project: Project, stem_files: dict[str, Path], bpm: float) -> str:
    tpl = _load_template()
    # счётчик Id выше максимального в шаблоне — иначе наши дорожки
    # пересекаются с PointeeId мастер-дорожки (PointeeId used 2 times)
    max_id = max((int(m) for m in re.findall(r'\sId="(\d+)"', tpl)),
                 default=1000)
    _id[0] = max_id + 1000
    midi_skel = _skeleton(tpl, "MidiTrack")
    audio_skel = _skeleton(tpl, "AudioTrack")

    tracks: list[str] = []
    for i, t in enumerate(project.tracks):
        color = TRACK_COLORS[i % len(TRACK_COLORS)]
        if t.notes:
            tracks.append(_clone_track(midi_skel, f"{t.stem} (MIDI)", color,
                                       midi_clip(t, bpm), "Midi"))
        if t.audio and t.audio.exists():
            wav = stem_files.get(t.stem, t.audio)
            end_beats = 4.0
            if t.notes:
                end_beats = max(end_beats,
                                max(n.start + n.duration for n in t.notes)
                                * bpm / 60)
            tracks.append(_clone_track(audio_skel, t.stem, color,
                                       audio_clip(wav, end_beats, bpm), "Audio"))

    # return-дорожки шаблона сохраняем — сенды микшера ссылаются на них
    returns = re.findall(r'\t\t\t<ReturnTrack[ >].*?\t\t\t</ReturnTrack>',
                         tpl, re.S)

    # заменяем все дорожки шаблона нашими + return-дорожками
    start = tpl.find("\t\t<Tracks>")
    end = tpl.find("\t\t</Tracks>") + len("\t\t</Tracks>")
    xml = tpl[:start] + "\t\t<Tracks>\n" + "\n".join(tracks + returns) + \
        "\n\t\t</Tracks>" + tpl[end:]
    # темп проекта: ручное значение + автоматизация (конверт темпа
    # перекрывает ручное значение, заменяем оба)
    xml = re.sub(r'(<Tempo>\s*<LomId Value="0" />\s*<Manual Value=")[^"]*(")',
                 rf'\g<1>{bpm:.2f}\g<2>', xml, count=1)
    xml = re.sub(r'(<FloatEvent Id="0" Time="-63072000" Value=")[^"]*(")',
                 rf'\g<1>{bpm:.2f}\g<2>', xml)
    # NextPointeeId выше всех выданных Id — Live иначе считает сет битым
    xml = re.sub(r'(<NextPointeeId Value=")\d+(")',
                 rf'\g<1>{_id[0] + 100}\g<2>', xml)
    return xml


def write_als(project: Project, out_als: Path, stem_files: dict[str, Path],
              bpm: float) -> Path:
    xml = build_xml(project, stem_files, bpm)
    out_als.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_als, "wb") as f:
        f.write(xml.encode("utf-8"))
    return out_als
