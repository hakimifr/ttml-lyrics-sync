# ttml-lyrics-sync

Thanks (fuck you) for the confusion Apple. AMLL editor deviating isn't helpful
either.

The official ttml samples were pulled by me directly from apple's API.

I created this skill because I'm so done editing every ttml
produced by AMLL editor by hand (because they deviate on a few places). Let the
clanker do it! Also fun fact,
[Apple's ttml docs](https://help.apple.com/itc/videoaudioassetguide/#/itcd7579a252)
says it's itunes:song-part, but in reality, out of all official ttml I pulled,
none of them were that but instead itunes:songPart. Oh Apple...

Everything below this is AI slop by claude (still worth reading, they're based
on my findings. I mean the whole skill is slop, but let's not think about
that). 

---

An agent skill for working with **Apple Music TTML lyric files** (`.ttml`) at
any sync level — line-synced, word-synced, or syllable-synced.

It exists because this format has a lot of Apple-specific convention layered
on top of generic TTML, and most of it is undocumented, mis-documented, or
only discoverable by reading real files. Getting a detail wrong — one
misplaced space — silently changes what the file means without producing a
parse error.

Everything here is verified against real files pulled from Apple's API, which
are included in the repo as the evidence base.

---

## What's in here

```
SKILL.md                     entry point — workflows and the easy-to-get-wrong list
references/ttml-format.md    the full format reference (14 sections)
scripts/syllabify_en.py      English word→syllable splitter, with self-validation
official_ttml_samples/
  line/                      3 line-synced files from Apple's API
  word_syllable/             4 span-synced files from Apple's API
amll_edited_ttml/            3 AMLL editor outputs — counter-examples, not models
```

The sample directories aren't decoration. When a structural question isn't
settled by the reference doc, the intended workflow is to **grep the official
samples** rather than reason from the TTML spec. Section 13 of the reference
indexes what each file demonstrates.

## Using it as a skill

Clone into your skills directory:

```bash
git clone <this-repo> ~/.claude/skills/ttml-lyrics-sync
```

It then triggers on any mention of a `.ttml` lyric file, `itunes:timing`,
`itunes:songPart`, `ttm:agent`, `ttm:role="x-bg"`, sync-level conversion, or
cleaning up AMLL editor output.

## Using the script standalone

```bash
python3 scripts/syllabify_en.py input.ttml output.ttml
python3 scripts/syllabify_en.py input.ttml --check    # dry run, no write
```

It splits whole-word `<span>`s into per-syllable spans, validates its own
output, and **refuses to write anything if a check fails**. A successful run
means XML well-formedness, `<p>` count, total text content, span count, x-bg
wrappers, `itunes:key` and `ttm:agent` all survived intact.

It deliberately leaves alone: line-synced `<p>`s, multi-word spans, `x-bg`
wrapper spans, inter-span whitespace, and the file's timing format.

**The timings it produces are evenly-divided placeholders, not real sync.** No
audio is analyzed. Both the split points and the timings need a
listen-through pass. English only.

---

## The format, briefly

The reference doc is the real answer; this is the short version of what people
get wrong.

**Sync level lives in the structure, not one attribute.** `itunes:timing` is
always present and is exactly `"Line"` or `"Word"` — there is no `"Syllable"`
value, so a syllable-synced file declares `"Word"`. It reliably tells you line
vs. span sync; it can't tell you word vs. syllable, because that isn't a file
property.

**Space between spans is structural.** No space = parts of the same word. One
space = a new word. That's the only signal — not timing continuity, not
punctuation. Never normalize whitespace between spans.

**A span is not necessarily one word or one syllable.** Some cover several
words when a passage is sung too fast for finer timing to matter — 80 of
Luther's 337 spans are multi-word. Split and unsplit words also mix freely
within a single file, and the same word may be split on one line and not the
next. That's deliberate authoring, not inconsistency to clean up.

**Agents:** `type` is `person`, `group`, or `other`, conventionally mapped to
`v1`/`v2`/`v3`, `v1000`, and `v2000`. The client only reads `type` — it drives
left/right display alignment. The ID numbering is convention, worth following
anyway. An agent may be self-closing *or* an open tag wrapping a
`<ttm:name type="full">` display name, so parsing code has to handle both — a
regex written only for `<ttm:agent ... />` silently misses every agent in a
file that uses the second form.

**Line sync is not a stripped-down mode.** It supports `itunes:key`,
`itunes:songPart`, and `ttm:agent` singers exactly as span sync does — one of
the official samples is line-synced with a named agent on all 44 of its lines,
`xmlns:ttm` and all. The only thing line sync genuinely cannot express is
background vocals, which need spans to attach to.

**Background vocals** are a nested `<span ttm:role="x-bg">` wrapper carrying
*no* `begin`/`end`, always placed last inside its `<p>` regardless of when it
actually occurs. Verified across all 56 instances in the corpus.

**Apple uses raw `'` and `"` in text**, not `&apos;`/`&quot;` — 237 raw
apostrophes and zero entities across the official corpus.

**Timing format is a per-file convention.** Bare seconds under a minute
switching to `M:SS.mmm` above it (Apple's dominant style), always-padded
`MM:SS.mmm`, or full `HH:MM:SS.mmm` — all three are genuine Apple output.
Detect what the file uses and match it; don't convert. Timestamps normally
carry three decimal places with trailing zeros kept, though one sampled file
strips them, so parse 1–3 decimals but emit 3.

### Apple's documentation is wrong about `itunes:songPart`

Apple's published docs call it `itunes:song-part`. Across every official file,
it is camelCase **`songPart`** — not one instance of the hyphenated form. It's
optional, appears only on `<div>` (never `<p>`), and takes one of eight
values: `Verse`, `Chorus`, `PreChorus`, `Bridge`, `Intro`, `Outro`, `Refrain`,
`Instrumental`. The last two are legal but haven't turned up in a sampled file
yet.

Treat this as a general warning: if you consult Apple's docs for anything in
this format, verify the claim against a real file first.

---

## Why AMLL output is separated out

The [AMLL TTML editor](https://github.com/amll-dev/amll-ttml-tool) is a useful
authoring tool, but its output deviates from Apple's format. This skill
targets **Apple's format**, and `amll_edited_ttml/` is included so those
deviations can be recognized and corrected — not reproduced.

The substantive ones:

| Deviation | Correct Apple behaviour |
|---|---|
| `itunes:timing` missing on span-synced output | always present, `"Word"` |
| `xml:lang` missing | always present |
| `xmlns:tts` and `xmlns:amll` declared but never used | never declared |
| `itunes:songPart` stripped from every `<div>` | present on most `<div>`s |
| `begin`/`end` added to the `x-bg` wrapper | wrapper carries `ttm:role` only |
| `<translations/>` dropped | present on all official samples |
| `leadingSilence` dropped | preserved |
| apostrophes escaped to `&apos;` | raw `'` |

Namespace ordering and `<p>` attribute ordering also differ, but those are
cosmetic. Timing style is *not* a deviation — the editor's always-padded
`MM:SS.mmm` also occurs in official Apple output.

**The `songPart` loss is unrecoverable.** Once a file has been round-tripped
through the editor, its section labels are gone and can only be re-derived
from the song structure by ear — never guessed. SKILL.md has an ordered
normalization workflow.

---

## Scope and caveats

- The format reference is grounded in **7 official files**. It describes what
  Apple demonstrably does, not a specification. Where something is convention
  rather than a hard rule, the doc says so.
- The AMLL deviation list comes from **3 sample files** and is not a spec of
  that editor — a different version may deviate differently.
- The syllabifier is a **textual heuristic**, not a phonetic or dictionary
  lookup, and only English is implemented. It cannot know how a word is
  actually sung. Note that `xml:lang` is a weak language signal on its own:
  one official sample has Malay lyrics tagged `xml:lang="en"`.
