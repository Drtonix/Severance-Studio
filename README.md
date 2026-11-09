# Severance Studio

A companion workstation for Ableton Live: drop a track, get stems, per-instrument
MIDI piano rolls and prompt-designed singing voices — export it all straight
into a Live project. Runs entirely on your Mac.

[Русский](#severance-studio-1)

## What it does

**Split.** A file or a link (YouTube, VK, SoundCloud — anything yt-dlp opens)
is separated into vocals, drums, bass, guitar, keys and finer parts, the same
engine as [Severance](https://github.com/Drtonix/Severance).

**Transcribe.** Every stem becomes a MIDI piano roll: Basic Pitch for melodic
parts, a dedicated drum transcription for percussion. Edit notes in the
built-in piano roll, preview with any instrument sound — change the sound,
keep the roll.

**Voices.** Design a singing voice from a text prompt ("your own Hatsune
Miku") — no recording of yourself needed. A voice-design TTS generates sample
speech from the prompt, the timbre is captured and a singing-voice-conversion
pipeline renders it onto your track's melody and lyrics. Russian and English.

**Export to Ableton.** One click: stems + MIDI clips + tempo map + key,
packed as an `.als` project (or plain drag-and-drop files) ready to open in
Live 11/12.

## Requirements

Apple Silicon, macOS 14 or newer.

| Model | Size | Needed for |
|---|---|---|
| HTDemucs (MLX) | 0.1 GB | stems |
| Basic Pitch (CoreML) | 0.1 GB | piano rolls |
| Whisper large-v3 | 2.9 GB | lyrics |
| Qwen3-TTS VoiceDesign | 8.4 GB | prompt voices |
| beat-this, lv-chordia | small | tempo, key, chords |

## Status

Early scaffold. Roadmap:

1. Project shell + stems → MIDI pipeline
2. Piano-roll editor with swappable instrument preview
3. Ableton export (.als generator, tempo map)
4. Voice lab: prompt-designed voices, singing conversion (RU/EN)

## License

MIT
