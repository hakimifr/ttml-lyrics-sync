---
name: ttml-lyrics-sync
description: >-
  Work with Apple Music TTML lyric files (.ttml) in untimed
  (itunes:timing=None), line-synced, word-synced, or syllable-synced form.
  Use whenever a .ttml lyric file is mentioned, inspected, edited,
  converted, or created; when handling itunes:timing/key/songPart,
  ttm:agent singers, ttm:role=x-bg background vocals, timing formats,
  span whitespace, or AMLL-editor cleanup; or when converting English
  line/word sync to syllable spans. Read the bundled format reference
  before markup changes: it is self-contained operational documentation
  of Apple's actual format, including where Apple's published docs are
  wrong. The sample TTML files are builder/regression fixtures, not
  required reading for normal skill use.
---

# Apple Music TTML Lyrics

## Before touching any TTML lyric file

**Read `references/ttml-format.md` first.** It documents the exact,
verified structure of this format - namespaces and required attributes,
`<head>`/`<body>`/`<div>`/`<p>` layout, agents, song parts, untimed and
timed modes, background vocals, text escaping, and (critically) the
whitespace convention that distinguishes a new syllable from a new word.
Getting that whitespace rule wrong silently changes what the file means
without causing an XML parse error, so read it in full rather than
skimming - do this even if you think you already know TTML, since this
format has Apple-specific conventions layered on top of generic TTML.

**Apple's format is the target.** The reference was derived from files
pulled straight from Apple's API. It is not an "AMLL-style" skill: the AMLL editor is a useful
authoring tool but its output deviates from Apple's format in several
specific ways, and this skill's job is to produce Apple-conformant files,
not to imitate the editor.

**Note on Apple's published documentation:** it has been observed to be
wrong about this format. The clearest example is `itunes:songPart`, which
Apple's docs call `itunes:song-part`; Apple's actual files use camelCase
`itunes:songPart` in every observed occurrence. Trust the reference's verified rules over the generic
TTML spec or Apple's prose documentation.

## What this skill covers

1. **Reading/inspecting** a TTML lyric file and correctly explaining its
   sync level, agents, song parts, and structure.
2. **Editing** a file (fixing a word, adjusting a timestamp, adding a
   line) without breaking its structural conventions.
3. **Converting line- or word-synced lyrics to syllable-synced** using the
   bundled English heuristic splitter (`scripts/syllabify_en.py`).
4. **Normalizing AMLL editor output** back to Apple's format.
5. **Creating a new file from scratch** at any sync level.

## Bundled sample files

| Directory | What it is | How to use it |
|---|---|---|
| `official_ttml_samples/no_timing/` | Untimed output from Apple's API | Builder/regression fixture for `itunes:timing="None"` |
| `official_ttml_samples/line/` | Line-synced output from Apple's API | Builder/regression fixtures |
| `official_ttml_samples/word_syllable/` | Span-synced output from Apple's API | Builder/regression fixtures |
| `amll_edited_ttml/` | Files produced by the AMLL editor | Builder regression fixtures for deviations |

**Do not require these samples for ordinary tasks.** `SKILL.md` plus
`references/ttml-format.md` must be sufficient to inspect, edit, create,
normalize, and convert TTML. Open samples only when maintaining the skill,
regression-testing code, or investigating a shape the reference genuinely
does not cover. Treat AMLL files strictly as counter-examples, never as a
model to copy.

## Things that are easy to get wrong

These come up repeatedly; the reference doc has the detail.

- **`itunes:timing` and `xml:lang` are always present on `<tt>`** in
  Apple's files. `itunes:timing` is exactly `"None"`, `"Line"`, or
  `"Word"`; there is no `"Syllable"` value, so syllable sync declares
  `"Word"`.
  If either attribute is missing, the file has been through a
  non-Apple tool; restore it.
- **`itunes:timing="None"` is valid untimed Apple output.** It uses plain
  lyric text in `<p>` elements, with no `<body dur>` and no `begin`/`end`
  on `<div>` or `<p>`. The observed sample's `<div>`/`<p>` tags are
  otherwise attribute-free, but preserve non-timing metadata if present
  in another file. The client cannot auto-scroll; the user scrolls
  manually. Never reinterpret it as malformed Line sync or fabricate
  timestamps. Timed conversion requires separately authored timing data.
- **Line sync is not a stripped-down mode.** It supports `itunes:key`,
  `itunes:songPart`, and `ttm:agent` singers - including several agents
  for a duet - exactly as span sync does. `xmlns:ttm` therefore appears
  on line-synced files that name singers, and its presence there is not
  an error to clean up. The one thing line sync genuinely cannot express
  is background vocals, which need spans to attach to.
- **`<ttm:agent>` has two spellings**: self-closing, or an open tag
  wrapping a `<ttm:name type="full">` display name. Parsing code that
  only matches `<ttm:agent ... />` will silently miss every agent in a
  file that uses the second form.
- **A span is not necessarily one word or one syllable.** Some spans
  cover several words when a passage is sung too fast for finer timing to
  matter (80 of Luther's 337 spans are multi-word). Never assume
  one-span-equals-one-word when counting or transforming.
- **Granularity mixes freely within one file.** Split and unsplit words
  sit side by side, the same word may be split on one line and not
  another, and a whole section may stay at word level while the rest of
  the song is syllable-level. This is deliberate authoring, not
  inconsistency to clean up.
- **Space between spans is structural.** No space = same word; one space
  = new word. Never normalize whitespace between spans.
- **`ttm:role="x-bg"` wrappers carry no `begin`/`end`** in Apple's files,
  and always sit last inside their `<p>`.
- **Apple uses raw apostrophes and quotes in text**, not
  `&apos;`/`&quot;`. Both ASCII `'` and typographic `’` occur; preserve
  whichever form the file already uses.
- **Match the file's existing timing format** rather than imposing one.

### Classify the mode before editing

Use this decision table; do not infer from filenames:

| Root value | Required content/timing shape | Meaning |
|---|---|---|
| `itunes:timing="None"` | Plain-text `<p>`; no `<body dur>`, no `<div begin/end>`, no `<p begin/end>` | Untimed, manual scrolling; preserve any non-timing metadata |
| `itunes:timing="Line"` | Plain-text `<p begin end>`; timed `<body>`/`<div>` | One timestamp interval per line |
| `itunes:timing="Word"` | Timed `<span begin end>` inside timed `<p>` | Word/syllable sync; inspect span spacing for granularity |

If root value and structure disagree, preserve the lyric text and report
the inconsistency. Do not silently choose a mode or invent missing timing.

## Workflow: converting line/word-synced -> syllable-synced (English)

1. Confirm the mode using the decision table above. Plain text alone is
   not enough to distinguish `"None"` from `"Line"`; check whether line
   timing attributes actually exist. If `itunes:timing="None"`, stop:
   the file has no timing data and this
   script cannot create valid timed lyrics from it. Ask for or author
   timings separately; do not infer them from line order or song length.
2. Confirm the lyrics are **English**. See the language limit below.
3. Save/copy the input somewhere writable if it isn't already.
4. Run:
   ```bash
   python3 scripts/syllabify_en.py <input.ttml> <output.ttml>
   ```
   For a line-synced input, the script tokenizes each plain-text line
   while preserving its whitespace, syllabifies each token, and divides
   the line duration evenly across all emitted syllable spans. It changes
   `<tt>`'s `itunes:timing` from `"Line"` to `"Word"`. These are
   placeholder timings, just like the word-synced path, and must be
   manually resynced by ear.
   The script validates its own output and **refuses to write anything if
   a check fails**, so a successful run means XML well-formedness, `<p>`
   count, total text content, span count, x-bg wrappers, `itunes:key` and
   `ttm:agent` all survived intact. Use `--check` in place of the output
   path for a dry run.
5. **Still spot-check by eye before presenting anything**, especially
   lines with contractions, quoted dialogue, or unusual tokens (numbers,
   abbreviations, stylized spellings) - the automated checks prove
   nothing was lost or malformed, not that the split points are *good*.
6. Read the script's summary line about what it left alone (multi-word
   spans, words too short to split) and pass anything notable on to the
   user.
7. Present the output and **always disclose the limitations** below.

### Language limit

**Only English is implemented and verified.** Do not use this script on
Malay/Indonesian or any other language, and do not improvise
syllabification rules for one - say plainly that the skill doesn't cover
it. Note that `xml:lang` is not a reliable language check on its own: one
official sample has Malay lyrics tagged `xml:lang="en"`. Judge from the
lyrics themselves.

### Limitations to disclose every time

- The timings it produces are **evenly-divided placeholders, not real
  sync.** No audio is analyzed.
- It is a **text-only heuristic**, not a phonetic or dictionary lookup.
  Real vocal delivery can split, merge, or stretch syllables differently
  from print hyphenation.
- Morpheme-boundary ambiguity (whether a vowel pair is a true diphthong
  or two separate word-parts) can only be handled by explicit
  special-casing; the script special-cases what's been seen so far, not
  every possible word.
- **Never present its output as finished, audio-verified sync data.**
  Both the split points and the timings need a listen-through pass.

## Workflow: normalizing AMLL editor output

Reference doc section 12 has the full deviation table with per-item
detail. Working order, highest value first:

1. **Restore `itunes:timing`** on `<tt>` according to structure and
   timing presence: `"None"` for truly untimed plain text, `"Line"` for
   timed plain-text lines, `"Word"` for timed spans. Do not use `"None"`
   merely as a fallback when a malformed file has lost attributes.
2. **Restore `xml:lang`.** If the original Apple file isn't available to
   copy it from, ask the user rather than guessing.
3. **Remove the unused `xmlns:tts` and `xmlns:amll` declarations.**
   Verify nothing in the file actually references those prefixes first
   (in the samples, nothing does).
4. **Strip `begin`/`end` from `ttm:role="x-bg"` wrapper spans**, leaving
   the inner spans' timings alone.
5. **Restore `<translations/>`** inside `<iTunesMetadata>`.
6. **Restore `leadingSilence`** if the original had it.
7. **Convert `&apos;` back to raw `'`** to match Apple's convention.
8. **Flag the lost `itunes:songPart` labels.** The AMLL editor strips
   them from every `<div>`, and they cannot be recovered from the file -
   only re-derived from the song structure. Tell the user they're gone
   rather than inventing section labels. If they want them back, work
   from the original Apple file if one exists; otherwise it's a listening
   task.

Items 1-8 are substantive. Namespace ordering and `<p>` attribute
ordering are cosmetic - only touch them if the user wants a byte-level
match with Apple's output. **Timing style is not a deviation**: the
editor's always-padded `MM:SS.mmm` also occurs in official Apple files,
so leave it as found.

Always diff your result against the input and confirm the lyric text and
all timings are unchanged before handing it back.

## Reference files

- `references/ttml-format.md` - the full structure reference, with an
  AMLL deviation table (§12), a sample-file index (§13), and a
  pre-handback checklist (§14). Read before any TTML task.
- `official_ttml_samples/`, `amll_edited_ttml/` - the evidence base.
- `scripts/syllabify_en.py` - the English syllable splitter, with
  built-in validation. Runnable standalone; also importable.
