# Apple Music TTML Lyric Format — Detailed Reference

This describes the TTML lyric format **as Apple Music actually emits it**,
verified against the files in `official_ttml_samples/` (pulled directly
from Apple's API): one untimed file, four line-synced files, and six
word/syllable-synced files. Every claim below was checked against that corpus, not assumed
from the TTML spec in the abstract — this format has Apple-specific
conventions layered on top of generic TTML.

**Apple's official format is the target.** The AMLL (Apple Music-like
Lyrics) editor produces files that deviate from it in several specific
ways; those deviations are documented in §12 so they can be recognized
and corrected, **not** so they can be reproduced. Samples of AMLL output
live in `amll_edited_ttml/`. When this document says "official", it means
Apple's own output.

Structural example snippets below use invented placeholder words rather
than real lyrics. **This reference is the operational source of truth:**
an agent using the skill should not need to open the bundled TTML samples
for ordinary inspection, editing, conversion, or generation tasks. The
samples are builder/regression evidence for extending or challenging this
reference, not a prerequisite for using it.

## Contents

1. Timing modes and sync granularity
2. Root element, namespaces, and required attributes
3. Head, agents, translations, romanization, and metadata
4. Body and div sections
5. Lyric-line (`p`) structure
6. Untimed and line-synced content
7. Word-synced content
8. Syllable spacing rule
9. Timestamp formats
10. Background vocals
11. Text characters and XML entities
12. AMLL editor deviations
13. Builder-only sample index
14. Pre-handback checklist

---

## 1. Timing modes and sync granularity

| `itunes:timing` / level | What gets its own timestamp | Typical use |
|---|---|---|
| **`None` / Untimed** | Nothing | Static lyrics; the user scrolls manually |
| **Line** | Each full line of text | Simplest, lowest-effort lyric files |
| **Word** | Each individual word | Standard karaoke-style highlighting |
| **Syllable** | Each syllable within a word | Apple Music's precise "bouncing ball" style |

There are three root timing values but four useful granularity labels:

- **`itunes:timing` is exactly `"None"`, `"Line"`, or `"Word"`.** There
  is no `"Syllable"` value. A syllable-synced file declares
  `itunes:timing="Word"` — see §2.
- **`None` is intentional, not malformed Line sync.** Its `<p>` elements
  contain plain lyric text, but there are no `begin`/`end` timestamps on
  `<p>` or `<div>` and no `dur` on `<body>`. The client cannot
  auto-scroll or highlight against playback; the user scrolls manually.
- **Word and syllable sync are not separate file types in practice.**
  They are two ends of a spectrum that coexist inside a single file: the
  same song routinely has some words split into syllable spans, some
  words as one span, and some spans covering *several* words. See §7–§8.
  This is why the samples directory is named `word_syllable/` rather
  than having separate `word/` and `syllable/` folders.

---

## 2. Root `<tt>` element, namespaces, and required attributes

```xml
<tt xmlns="http://www.w3.org/ns/ttml"
    xmlns:itunes="http://music.apple.com/lyric-ttml-internal"
    xmlns:ttm="http://www.w3.org/ns/ttml#metadata"
    itunes:timing="Word"
    xml:lang="en">
```

Across all eleven official samples the `<tt>` attribute set is
**consistent, with one conditional namespace**:

| Attribute | Untimed (`None`) | Line-synced | Word/syllable-synced |
|---|---|---|---|
| `xmlns` (default TTML ns) | Always | Always | Always |
| `xmlns:itunes` | Always | Always | Always |
| `xmlns:ttm` | Only if the file uses `ttm:*` | Only if the file uses `ttm:*` | Always in the corpus |
| `itunes:timing` | `"None"` | `"Line"` | `"Word"` |
| `xml:lang` | Always | Always | Always |

- **`xmlns:ttm` is present whenever the file references anything in that
  namespace, at any sync level.** For word/syllable files that is always,
  since they use `<ttm:agent>` and/or `<span ttm:role>`. **Line-synced
  files vary: 2 of 4 in the corpus declare it.**

  A line-synced file needs `ttm` when it names singers — most obviously
  when a duet or group means several agents, but a vendor may also
  declare a single agent when nothing forces it. `#icanteven` does
  exactly that: line-synced, one `person v1` agent, `ttm:agent="v1"` on
  all 44 `<p>` elements, `xmlns:ttm` duly declared. `Not So Bad` also
  declares `person v1` and `person v2`; meanwhile `9 to 5` and `How Long`
  name no singers and correctly omit the namespace.

  **So don't treat `xmlns:ttm` on a line-synced file as an error, and
  don't strip it.** The rule is simply: declare it if and only if
  something in the file uses the prefix. Which of those two shapes you
  get for a given single-singer song is a lyrics-vendor styling choice,
  not a structural rule.
- **`xmlns:tts` and `xmlns:amll` never appear in official files.** Both
  are AMLL editor additions (§12). `tts` (TTML styling) is declared but
  never used; the `amll` namespace URI is a placeholder
  (`http://www.example.com/ns/amll`) and has no meaning to Apple Music.
- **Attribute order is stable** in the official corpus: default ns,
  `xmlns:itunes`, then `xmlns:ttm` if present, then `itunes:timing`,
  then `xml:lang`. Order is not semantically meaningful, but matching it
  costs nothing and keeps diffs against Apple's own files clean.

### `itunes:timing` — required, with three values

**This attribute is always present on official files, and its value is
one of exactly three strings:**

- `itunes:timing="None"` — the `<p>` elements contain plain text and no
  playback timings exist. `<body>` has no `dur`; `<div>` and `<p>` have
  no `begin`/`end`. Lyrics are manually scrolled.
- `itunes:timing="Line"` — the `<p>` elements contain plain text.
- `itunes:timing="Word"` — the `<p>` elements contain `<span>` elements.
  **This covers both word-synced and syllable-synced files.** There is
  no `"Syllable"` value.

So `itunes:timing` reliably distinguishes untimed, line-synced, and
span-synced files. It does **not** tell you how finely `"Word"` spans
are divided — that is a per-word authoring decision, readable only from
the actual span structure (§7–§8).

### Mode consistency matrix

Use all three signals together when inspecting or creating a file:

| Mode | `<body>` | `<div>` | `<p>` content |
|---|---|---|---|
| `None` | No `dur` | No `begin`/`end`; preserve other metadata | Plain text; no `begin`/`end`; no spans; preserve other metadata |
| `Line` | `dur` present | `begin`/`end` present | Plain text with `begin`/`end` on `<p>` |
| `Word` | `dur` present | `begin`/`end` present | `<p begin end>` containing timed spans |

If these disagree, the file is inconsistent. Do not “repair” it by
guessing: preserve lyric text, identify the conflicting fields, and ask
for the intended mode or source timing data. The one common recoverable
case is AMLL span output missing only `itunes:timing`; restore `"Word"`
when timed spans unambiguously establish the mode (§12).

If you encounter a span-synced file with `itunes:timing` **missing**,
it did not come from Apple — the AMLL editor omits it (§12). Restore it
as `itunes:timing="Word"`; do not treat its absence as a legitimate
format variant.

### `xml:lang` — required

Present on all eleven official samples. One caveat worth knowing: the value
reflects Apple's catalogue metadata, and can disagree with the actual
language of the lyrics — `9 to 5 (feat. khodi) - Lucidrari.ttml` has
Malay lyrics and `xml:lang="en"`. Don't "correct" it to match the lyrics
you see; don't infer the lyric language from it either. The AMLL editor
drops this attribute on span-synced files; restore it (§12).

---

## 3. `<head>` — agents, translations, romanization, and metadata

```xml
<head>
  <metadata>
    <ttm:agent type="person" xml:id="v1"/>
    <ttm:agent type="person" xml:id="v2"/>
    <ttm:agent type="group"  xml:id="v1000"/>
    <ttm:agent type="other"  xml:id="v2000"/>
    <iTunesMetadata xmlns="http://music.apple.com/lyric-ttml-internal"
                    leadingSilence="0.180">
      <translations/>
      <songwriters>
        <songwriter>Full Name</songwriter>
        <songwriter>Full Name</songwriter>
      </songwriters>
    </iTunesMetadata>
  </metadata>
</head>
```

### `<ttm:agent>` — singers

`type` takes exactly three values: **`person`**, **`group`**, **`other`**.

The `xml:id` values follow a strong convention:

| `xml:id` | `type` | Meaning |
|---|---|---|
| `v1` | `person` | Lead vocalist |
| `v2` | `person` | Second vocalist (duet) |
| `v3` | `person` | Third vocalist |
| `v1000` | `group` | Group/ensemble vocal |
| `v2000` | `other` | Everything else (spoken word, samples, uncredited parts) |

**What the client actually reads is `type`, not `xml:id`.** The type
drives display alignment — whether a line renders left-mounted or
right-mounted. The `vN` / `vN000` numbering is convention only; the
player does not parse meaning out of the digits. Follow the convention
anyway: it is what every official file does, and deviating from it makes
files harder to compare against Apple's own.

Observed in the corpus:

- `#icanteven` (**line-synced**) — one agent, `person v1`, carrying a
  `<ttm:name>` child.
- `Not So Bad` (**line-synced**) — two self-closing agents, `person v1`
  and `person v2`.
- `10:35` — one agent, `person v1`.
- `Luther` — `person v1`, `person v2`, `other v2000`, `group v1000`.
- `Popular` — `person v1`, `person v2`, `person v3`, `other v2000`,
  `group v1000`.
- `You` — `person v1`, `person v2`, `group v1000`, `other v2000`.
- `APT.` — `person v1`, `person v2`, `group v1000`.
- `OMG` — one agent, `person v1`.

Note that the *declaration order* of `v1000` and `v2000` varies between
files (`Luther` declares `v2000` before `v1000`, `You` the reverse), so
order carries no meaning. In every file, every declared agent is
actually used somewhere — Apple does not emit unused declarations.

### `<ttm:agent>` has two spellings

Usually it is an empty self-closing element:

```xml
<ttm:agent type="person" xml:id="v1"/>
```

But it can also be an open element wrapping a **`<ttm:name type="full">`**
child holding the performer's display name:

```xml
<ttm:agent type="person" xml:id="v1"><ttm:name type="full">The Neighbourhood</ttm:name></ttm:agent>
```

Only `#icanteven` does this in the current corpus (1 of 8 files that
declare agents at all), and the only observed `type` on `<ttm:name>` is
`"full"`. **Preserve a `<ttm:name>` if you find one** — don't collapse
the agent back to a self-closing tag, and don't invent names for agents
that don't have them. Code that parses agents must tolerate both
spellings; a regex written only for `<ttm:agent ... />` will silently
miss every agent in a file like this one.

### Agents on line-synced files

**Line sync fully supports agents**, and `#icanteven` demonstrates the
whole chain in a file with no spans at all: `xmlns:ttm` on `<tt>`, a
`<ttm:agent>` declaration in `<head>`, and `ttm:agent="v1"` on every
`<p>`. `Not So Bad` demonstrates two person agents and switches between
`v1` and `v2`; the other two line-synced samples simply don't name
singers.

So the presence or absence of agents says nothing about sync level, and
vice versa. See §10 for the one thing line sync genuinely cannot express.

### `<iTunesMetadata>`

- Re-declares the default namespace locally
  (`xmlns="http://music.apple.com/lyric-ttml-internal"`). This is
  correct and expected, not a typo: it sits inside the ttml-namespaced
  `<metadata>` but belongs to the iTunes schema.
- **`leadingSilence="..."`** — optional attribute, observed as `"0"`,
  `"0.100"`, `"0.180"`, `"0.200"`. Present on 7 of 11 official samples.
  Preserve it when editing; the AMLL editor drops it.
- **`<translations>`** — present on **all eleven** official samples.
  It is self-closing as `<translations/>` when no translation exists,
  and contains subtitle tracks when translations are available. See the
  complete schema below. Do not assume it is always empty.
- **`<songwriters><songwriter>Name</songwriter>…</songwriters>`** — one
  element per credited writer, present on every official sample.
- **`<audio lyricOffset="0.882" role="spatial"/>`** — optional metadata
  observed on `OMG`. Its broader value set and semantics are not verified;
  preserve it exactly rather than adding, removing, or recalculating it.

### Translations

Translations live under the iTunes-namespace `<iTunesMetadata>` element,
not beside the timed lyric `<p>` elements:

```xml
<translations>
  <translation type="subtitle" xml:lang="en-US">
    <text for="L1">Translated full line</text>
    <text for="L2">Translated main line <span xmlns="http://www.w3.org/ns/ttml" xmlns:ttm="http://www.w3.org/ns/ttml#metadata" ttm:role="x-bg">(Translated background)</span></text>
  </translation>
</translations>
```

- The observed track is `<translation type="subtitle" xml:lang="en-US">`.
  `xml:lang` identifies the translation's target language; preserve the
  actual BCP 47 value rather than replacing it with the root language.
- Each iTunes-namespace `<text for="L…">` maps to the body `<p>` carrying
  the same `itunes:key`. Resolve by the `for` value, **not child order**:
  official translation entries are not necessarily sorted numerically.
- Translation is **per-line only**. The `<text>` content is an untimed
  rendering of the complete translated line. Per-word translation is not
  a supported or meaningful shape; do not put timed word spans around a
  translation.
- If the source line has x-bg, the translated line may mirror it with an
  untimed TTML `<span ttm:role="x-bg">` containing direct text. Preserve
  the wrapper's position: official metadata examples include both trailing
  and leading x-bg.
- When no translation exists, keep the standard empty `<translations/>`
  container. Never invent translated text.

### Transliterations / romanization

Apple calls the metadata track a **transliteration**; for Korean `*-Latn`
tracks this is the romanization shown by the client. The two observed
official files use per-word timed romanization:

```xml
<transliterations>
  <transliteration xml:lang="ko-Latn">
    <text for="L1">
      <span begin="6.677" end="7.066" xmlns="http://www.w3.org/ns/ttml">a</span> <span begin="7.066" end="7.439" xmlns="http://www.w3.org/ns/ttml">pa teu</span>  <span begin="7.439" end="7.646" xmlns="http://www.w3.org/ns/ttml">a</span>
    </text>
  </transliteration>
</transliterations>
```

- `<transliterations>` is optional. Its observed child is
  `<transliteration xml:lang="ko-Latn">`; `OMG` additionally has
  `automaticallyCreated="true"`, while `APT.` does not. Preserve that
  provenance attribute if present; do not add it by inference.
- Each `<text for="L…">` maps to the same keyed body line. In both files,
  every body key has exactly one translation entry and one transliteration
  entry, but consumers must still map by key rather than position.
- For observed **per-word romanization**, every ordinary romanization
  span has the exact `begin`/`end` pair of its corresponding body lyric
  span. The span text is replaced with its romanized reading. Do not
  redistribute or independently retime it.
- Romanization whitespace is its own alignment syntax. In the Korean
  samples, a single space can separate romanization spans within one
  original Korean word, while a double space marks an original word
  boundary. This differs from body lyric spacing (§8). Preserve every
  whitespace character exactly; never run generic whitespace cleanup on
  a transliteration track.
- x-bg is mirrored at the same structural position. Its wrapper still has
  no `begin`/`end`; in per-word romanization its inner spans retain the
  body background spans' exact timings. A translation's x-bg, by contrast,
  is untimed direct text.
- Apple also supports **per-line romanization**, but no official per-line
  sample is currently bundled and Apple has not documented the exact XML
  shape clearly enough to reconstruct it safely. Preserve such a track if
  encountered; do not convert between line and word granularity or invent
  a per-line serialization without a verified source.

---

## 4. `<body>` and `<div>`

```xml
<body dur="2:57.598" ttm:agent="v2">
  <div begin="9.986" end="12.721" itunes:songPart="Intro" ttm:agent="v2000">
    <p …>…</p>
  </div>
  …
</body>
```

### `<body>`

- `dur="..."` — total song duration, following the file's timing
  convention (§9). Required for `itunes:timing="Line"` and `"Word"`;
  absent in the observed `"None"` shape because the file contains no
  playback timing information.
- `ttm:agent="..."` — **optional default agent for the whole song**,
  observed on `Luther` and `You` (both `ttm:agent="v2"`). A `<p>` with
  its own `ttm:agent` overrides it. Preserve this attribute if present;
  don't add one that wasn't there.

Agent inheritance is most-specific-wins: `<p ttm:agent>` overrides
`<div ttm:agent>`, which overrides `<body ttm:agent>`. Every referenced
ID must have a matching `<ttm:agent xml:id="...">` declaration in
`<head>`.

### `<div>` — song sections

Observed attribute shapes across the official corpus:

```
no attributes                             (7 — untimed)
begin end                                (21 occurrences)
begin end itunes:songPart                (39)
begin end itunes:songPart ttm:agent      (23)
```

- For `itunes:timing="None"`, a section may be plain `<div>` with no
  attributes. Its purpose is still to group lyric lines; it carries no
  playback interval and no observed `itunes:songPart`.

- **`itunes:songPart` is optional** — 21 of 83 timed official `<div>`s
  have none, and one whole timed file uses none at all. The observed
  untimed file has seven attribute-free `<div>`s.
- **Note the attribute name: `itunes:songPart`, camelCase.** Apple's
  published documentation calls it `itunes:song-part` (kebab-case).
  **The documentation is wrong.** Across every observed occurrence in
  files pulled from Apple's API, it is `songPart` — not one instance of
  `song-part`. Bear
  this in mind if consulting Apple's docs again for anything else in
  this format; they have been observed to be inaccurate.
- **`itunes:songPart` appears only on `<div>`, never on `<p>`** (0
  occurrences on `<p>` across the corpus).
- Observed values, with counts across the corpus:

  | Value | Count | Notes |
  |---|---|---|
  | `Verse` | 27 | |
  | `Chorus` | 18 | |
  | `PreChorus` | 7 | camelCase, no hyphen or space |
  | `Bridge` | 4 | |
  | `Intro` | 3 | |
  | `Outro` | 3 | |
  | `Refrain` | 0 | valid, but rare — not yet seen in the wild |
  | `Instrumental` | 0 | valid, but rare — not yet seen in the wild |

  Those eight are the full set. `Refrain` and `Instrumental` are legal
  values that simply haven't turned up in a sampled file yet; don't
  treat encountering one as an error, and don't invent values outside
  this list.
- `ttm:agent` on a `<div>` sets the agent for that whole section; it
  always appears **after** `itunes:songPart` in official files.
- A `<div>` groups one or more `<p>` lines. **Grouping granularity
  varies:** `9 to 5` uses one `<div>` for the entire song, while
  `Popular` uses one `<div>` per section. Both are valid — match
  whatever the file you're editing already does, and don't merge or
  split `<div>`s during a sync-level conversion.
- In timed modes, a `<div>`'s `begin`/`end` spans the min/max of the
  `<p>` elements it contains. Treat that as observed convention rather
  than something to recompute unprompted. Untimed `<div>`s have neither.

---

## 5. `<p>` — one per line

Observed attribute shapes:

```
no attributes                     (28 occurrences — untimed)
begin end                        (95 occurrences — one line-synced file)
begin end itunes:key             (47 — one line-synced file)
begin end itunes:key ttm:agent   (464 — all 6 word/syllable files, plus 2 line-synced)
```

The no-attribute shape identifies the observed untimed mode. The other
three all occur on line-synced files, so attributes alone do not
distinguish line from word/syllable sync — inspect the content (§6–§8).

```xml
<p begin="18.030" end="21.740" itunes:key="L2" ttm:agent="v1">
  …line content…
</p>
```

- **`begin` / `end`** — the line's overall timing. Required for Line and
  Word modes; absent for `itunes:timing="None"`.
- **`itunes:key="L1"`, `"L2"`, `"L3"`…** — sequential line numbering
  across the **entire song**, not reset per `<div>`. Always present on
  every `<p>` in word/syllable files. On line-synced files it is
  all-or-nothing per file: `How Long` (47 `<p>`s) and `#icanteven` (44)
  have it on every line, `9 to 5` on none of its 95. If a file uses it,
  keep the numbering contiguous when adding or removing lines.
- **`ttm:agent="v1"` / `"v2"` / `"v3"` / `"v1000"` / `"v2000"`** — which
  singer performs this line. Present on every `<p>` in word/syllable
  files, and on every `<p>` of one line-synced file (§3). If you add a
  `<p>` referencing an agent, that agent must be declared in `<head>`,
  and `xmlns:ttm` must be declared on `<tt>` (§2).
- **Content differs completely by sync level — see §6–§8.**

---

## 6. Untimed and line-synced `<p>` content

### Untimed (`itunes:timing="None"`)

Canonical shape:

```xml
<tt xmlns="http://www.w3.org/ns/ttml"
    xmlns:itunes="http://music.apple.com/lyric-ttml-internal"
    itunes:timing="None"
    xml:lang="en">
  <head>
    <metadata>
      <iTunesMetadata xmlns="http://music.apple.com/lyric-ttml-internal">
        <translations/>
        <songwriters><songwriter>Full Name</songwriter></songwriters>
      </iTunesMetadata>
    </metadata>
  </head>
  <body><div><p>Static lyric line</p></div></body>
</tt>
```

- `<body>` has no `dur`.
- `<div>` has no `begin`/`end`. The observed file has no other `<div>`
  attributes, but treat that as evidence rather than a prohibition:
  preserve non-timing metadata such as `itunes:songPart` or `ttm:agent`
  if an untimed file already contains it.
- `<p>` has no `begin`/`end` and contains plain text with no spans. The
  observed file also lacks `itunes:key` and `ttm:agent`; preserve either
  if encountered rather than stripping it merely because the mode is
  untimed.
- The client has no timing data for automatic scrolling or highlighting.
  The user scrolls the lyrics manually.
- Do **not** change `"None"` to `"Line"` merely because `<p>` contains
  plain text. A `"Line"` file must also provide line timings.
- Do **not** fabricate timings from the line order or track duration.
  Conversion to Line or Word/syllable sync requires separately authored
  timing data (normally listening to the audio). Text can be prepared or
  syllabified independently, but it cannot become valid timed TTML from
  this file alone.

### Line-synced (`itunes:timing="Line"`)

```xml
<p begin="00:00:14.630" end="00:00:18.030">Some example lyric line</p>
<p begin="00:18.31" end="00:21.666" itunes:key="L1" ttm:agent="v1">Another example line</p>
```

- **Plain text directly inside `<p>`. No `<span>` elements at all.**
- No word- or syllable-level timing — the whole line lights up at once.
- It can be converted directly to syllable sync by tokenizing each line
  and distributing its duration across the resulting spans. Such a
  conversion changes `<tt>`'s `itunes:timing="Line"` to `"Word"`; the
  generated timings are placeholders and require manual resyncing.
- **`itunes:key` and `ttm:agent` are both available here** (§5), as the
  second example shows. Line sync means "no per-word timing", not "no
  metadata".
- No `ttm:role="x-bg"` background vocals at this level (§10).

---

## 7. Word-synced `<p>` content

```xml
<p begin="18.030" end="21.740" itunes:key="L2" ttm:agent="v1">
  <span begin="18.030" end="19.267">Hello</span> <span begin="19.267" end="20.504">there</span> <span begin="20.504" end="21.740">world</span>
</p>
```

- **`<span begin="..." end="...">text</span>`**, with **a single literal
  space** between spans. That space is not pretty-printing — it is the
  structural token separator (§8).
- Attached punctuation stays inside the span with the word it belongs
  to: `<span …>world?</span>`.

### A span is not restricted to exactly one word

This is important and easy to get wrong. **A single span may cover two
or more whole words** when the delivery is fast enough that finer timing
would be pointless. For example, this is a verbatim extract from
`official_ttml_samples/word_syllable/Luther - Kendrick Lamar.ttml`:

```xml
<span begin="14.625" end="15.121">drop it</span> <span begin="15.121" end="15.505">like it's</span>
```

Each element above is one timed unit even though its text contains a
space. Official data also includes spans such as `you a`, `dreams and`,
and `in front of`. A space *inside* a span is ordinary text content, not
a separator between two timed units.

The reverse also happens: a stylized token can be split across spans
with **no space between them** even in an otherwise word-level file:

```xml
<span begin="4:10.718" end="4:10.891">4</span><span begin="4:10.891" end="4:11.064">L</span>
```

Both cases are the same underlying principle: **span boundaries follow
the vocal performance, not word boundaries.** Never assume one span
equals one word — when counting or transforming, treat span text as
opaque and preserve it.

---

## 8. Syllable-synced `<p>` content — THE CRITICAL RULE

```xml
<p begin="00:17.860" end="00:20.673" itunes:key="L1" ttm:agent="v1">
  <span begin="00:17.860" end="00:18.249">He</span><span begin="00:18.249" end="00:18.532">llo</span> <span begin="00:18.532" end="00:19.071">the</span><span begin="00:19.071" end="00:19.401">re</span>
</p>
```

Same `<span begin end>text</span>` pattern as §7, but a word is broken
into **multiple consecutive spans**.

- **The single rule that determines everything:**
  - **No space between two spans → they are parts of the *same* word.**
  - **A single literal space between two spans → a *new* word starts.**
- This is the *only* signal. It is **not** determined by:
  - **Timing continuity.** Two spans of the same word can have a real
    time gap between them (a held note or short pause) and still have no
    space in the markup. Two different words are never written with zero
    space just because they're sung back-to-back.
  - **Punctuation.** A trailing comma/question mark/paren attaches to
    the last span's text; a hyphen inside a span (`oh-`) is literal
    text, not a structural marker.

### Granularity is per word, and mixes freely within a file

**Not every word in a syllable-synced file is split, and this is normal,
not sloppiness.** Within one `itunes:timing="Word"` file you will find,
side by side:

- words split into syllable spans (`de` + `vil`),
- short or fast words left as one whole-word span,
- the *same word* split on one line and unsplit on another,
- single spans covering several words (§7),
- a `v2` duet or `v1000` group section done entirely at word level while
  the surrounding song is syllable-level.

Splitting is an authoring choice made per word, based on how the line is
actually sung. There is no consistency requirement to enforce and no
"complete the syllabification" cleanup to perform. When editing, leave
existing granularity decisions alone unless the task is specifically to
change them.

**When writing code to parse or generate this format: never regex or
string-split on generic whitespace to "clean up" the markup, and never
re-join spans with a normalized separator. The exact
single-space-vs-no-space pattern between spans must be preserved
byte-for-byte, or the file's meaning changes.** (Incidental double
spaces do occur in official files — `Luther` has 5 — so preserve what's
there rather than normalizing it.)

---

## 9. Timing format — `begin` / `end` values

Multiple concrete formats exist. **They are per-file conventions: detect
what the file already uses and match it exactly.** Do not assume one
universal format, and do not convert a file from one style to another.

- **Style A — bare seconds under a minute, `M:SS.mmm` at and above one
  minute.** The dominant official style: 8 of the 10 timed official samples,
  including every word/syllable file.
  - Under 60s: `"14.630"`, `"0.138"`, `"58.272"` — no minutes prefix.
  - 60s and over: `"1:01.000"`, `"5:57.630"` — seconds zero-padded to
    two digits, minutes **not** zero-padded.
  - `<body dur>` follows the same rule: `dur="2:57.598"`.
  - Note this means a single file mixes both shapes, switching at the
    one-minute mark.
- **Style B — always-padded `MM:SS.mmm`** with no hours field, used for
  every timestamp including those under a minute: `"00:18.310"`,
  `"04:06.760"`, with `<body dur="03:54.480">`. Observed on one official
  line-synced file (`#icanteven`) and on AMLL editor output.
- **Style C — full `HH:MM:SS.mmm`, zero-padded throughout**, likewise
  used for every timestamp: `"00:00:05.060"`, `"00:04:13.480"`, with
  `<body dur="00:04:57.030">`. Observed on one official line-synced file
  (`9 to 5`).

All three are genuine Apple output. Style A is by far the most common
and the only one seen on word/syllable files, but **none of the three is
"wrong"** — pick by reading the file, never by preference.

### Millisecond padding

Timestamps normally carry exactly **three decimal places**, with
trailing zeros kept for consistency (`"1:01.000"`, `"00:04:57.030"`).

One sample deviates: `#icanteven` strips trailing zeros, mixing 1, 2 and
3 decimal places within the same file (`"02:06.1"`, `"00:18.31"`,
`"00:21.666"`) — 0 of its 105 timestamps end in a zero digit, against
74–193 such values in every other official file. This is a rare
lyrics-vendor quirk, not the norm.

Practical consequence: **parsers must accept 1–3 decimal places**, but
**generators should emit 3** — that matches the overwhelming majority of
files, and a stripped file is not worth reproducing bug-for-bug.

Practical rule overall: read a couple of existing `begin`/`end` values
before writing any, and match their shape — the fields present, the
zero-padding, and the switch point if the file uses Style A.

---

## 10. Background vocals (`ttm:role="x-bg"`)

```xml
<p begin="1:26.859" end="1:30.321" itunes:key="L24" ttm:agent="v2">
  <span begin="1:26.859" end="1:27.221">Baby,</span> <span begin="1:27.221" end="1:27.616">you a</span> <span begin="1:27.616" end="1:28.192">star</span> <span ttm:role="x-bg"><span begin="1:29.847" end="1:30.320">(Right)</span></span>
</p>
```

- A background-vocal part is a **nested wrapper span** containing its
  own sequence of word/syllable spans, which follow all the same spacing
  rules (§7–§8) independently.
- **The body-lyric wrapper carries `ttm:role="x-bg"` and no timing — no
  `begin`, no `end`.** All 71 body x-bg wrappers across the official corpus
  are exactly `<span ttm:role="x-bg">`. The timing lives entirely on the
  inner spans. (The AMLL editor adds `begin`/`end` to the wrapper — §12.)
- **Placement is source-dependent.** 63 observed body wrappers are last
  inside `<p>`, while 8 in `OMG` are first; none are in the middle. Preserve
  the position already authored. Do not move a leading x-bg to the end
  merely to match the more common shape. The bundled Line-to-span heuristic
  below deliberately appends newly inferred x-bg last because that is the
  requested convenience convention, not a universal Apple constraint.
- When x-bg is trailing, a single literal space normally separates the
  last main-vocal span from the opening wrapper. When it is leading, its
  closing wrapper is followed by the separator before the main lyric.
- The text is conventionally wrapped in literal parentheses, `(`
  attached to the first inner span's text and `)` to the last — a
  display convention, not a structural requirement.

### Line-to-span conversion heuristic for parentheticals

When converting `itunes:timing="Line"` plain text to spans, balanced
parenthetical text attached to a non-parenthetical main line is usually a
background vocal. The bundled splitter therefore converts:

```xml
<p begin="10.000" end="14.000">Hello (yeah)</p>
```

to this structural shape (placeholder times abbreviated):

```xml
<p begin="10.000" end="14.000"><span begin="..." end="...">Hel</span><span begin="..." end="...">lo</span> <span ttm:role="x-bg"><span begin="..." end="...">(yeah)</span></span></p>
```

Rules:

- Move each balanced top-level `(...)` segment into one x-bg wrapper at
  the **end** of the `<p>`, even if it appeared in the middle of the
  source line. Preserve its source-order timing; wrapper placement is
  structural, not chronological.
- If several parenthetical segments occur on one line, put all of them
  in that one final wrapper, in source order, separated by one space.
- Preserve the literal opening and closing parentheses in inner span
  text. Whether a client hides them is the client's decision; the TTML
  vendor must not strip them.
- Put exactly one literal space between the last main-vocal `</span>`
  and `<span ttm:role="x-bg">`.
- Generate x-bg only when non-parenthetical main-vocal text also remains.
  A line consisting entirely of parenthetical text is not an independent
  x-bg line; keep it as ordinary main-vocal spans for manual editing.
- If parentheses are unbalanced, do not guess. Keep the line ordinary
  and report it for review.
- Empty `()` does not identify a vocal. Keep a line containing it
  ordinary rather than generating an empty-content x-bg.
- Apply this heuristic only to literal round parentheses `(...)`.
  Square `[...]` and curly `{...}` brackets remain ordinary lyric text.
- This is a high-probability authoring heuristic, not a semantic truth:
  manually review generated wrappers during the timing pass.
- **Constraint matrix:**

  | Sync level | `ttm:agent` singers | `ttm:role="x-bg"` background vocals |
  |---|---|---|
  | Untimed (`None`) | Not observed; preserve if encountered | **No** — no spans |
  | Line | **Yes** — confirmed in the corpus (`#icanteven`) | **No** |
  | Word | Yes | Yes |
  | Syllable | Yes | Yes |

  Background vocals need per-span structure to attach to, which
  line-synced `<p>` content (plain text) cannot express. **This is the
  only thing line sync genuinely cannot do** — agents, `itunes:key`,
  song parts and multiple singers all work fine at line level.

---

## 11. Text content: quotes, apostrophes, and entities

**Apple's official files use raw characters, not XML entities.** Across
all eleven official samples: **zero** occurrences of `&apos;`, `&quot;`,
or `&amp;`, against 410 raw ASCII apostrophes (`'`), 11 typographic
apostrophes (`’`), and 68 raw `"` in text content.

```xml
<span begin="17.602" end="17.802">don't</span>
<span begin="21.488" end="21.688">'cause</span>
<p begin="28.480" end="32.887" itunes:key="L5">She said, "Boy, tell me honestly</p>
```

This is valid XML — only `<` and `&` strictly require escaping in text
content; `'` and `"` do not (attribute values use `"` delimiters, so a
raw `"` in *text* is unambiguous). Apple takes advantage of that.

- Both plain ASCII `'` (U+0027) and typographic `’` (U+2019) occur in
  official text. Preserve the form already present; do not normalize
  apostrophes during an unrelated edit.
- The AMLL editor escapes apostrophes to `&apos;` (§12). That is
  well-formed and renders identically, so it isn't a correctness bug,
  but it doesn't match Apple's output.
- A literal `&` in lyric text must still be written `&amp;` — standard
  XML rules apply, it just hasn't come up in the sampled files.

**Critical implementation note:** any code that scans span text for
letters or vowels (syllabification, word counting) must handle **both**
forms:

1. **Raw apostrophes** are ordinary text characters sitting inside words
   — `don't`, `I’m`, `goin'`, `'cause`. Code that assumes a token is a
   clean `[A-Za-z]+` run will mis-handle contractions in real Apple files.
2. **Entity references, where present, are atomic opaque units.** Never
   scan their raw characters: `&quot;` contains the letters `q`, `u`,
   `o`, `t`, none of which belong to the word. Substitute each entity
   with a single non-alphabetic placeholder before analysis and restore
   it afterward.

`scripts/syllabify_en.py` implements both paths.

---

## 12. AMLL editor deviations — what to recognize and fix

The AMLL editor is a convenient authoring tool, but its output is not
Apple-conformant. Comparing `amll_edited_ttml/` against
`official_ttml_samples/`, these are the concrete differences:

| # | Deviation | Correct Apple behaviour |
|---|---|---|
| 1 | **`itunes:timing` missing** on span-synced output (`word.ttml` has none) | Always present; `"None"` for untimed, `"Line"` for line-synced, `"Word"` for span-synced (§2) |
| 2 | **`xml:lang` missing** on span-synced output (`word.ttml`, `syllable.ttml`) | Always present (§2) |
| 3 | **`xmlns:tts` declared but never used** | Never declared — no official file references the styling namespace |
| 4 | **`xmlns:amll="http://www.example.com/ns/amll"` declared** | Never declared — a placeholder namespace with no meaning to Apple Music |
| 5 | **`itunes:songPart` stripped from every `<div>`** (0 across all three files) | Optional, but Apple emits it on most `<div>`s (§4) — once dropped, the section labels are unrecoverable without re-authoring |
| 6 | **`begin`/`end` added to the `ttm:role="x-bg"` wrapper span** | Wrapper carries `ttm:role` only; timing lives on inner spans (§10) |
| 7 | **`leadingSilence` dropped** from `<iTunesMetadata>` | Preserved when the source had it (§3) |
| 8 | **Apostrophes escaped to `&apos;`** | Raw `'` (§11) |
| 9 | **Namespace declaration order shuffled**, `itunes` last | `xmlns`, `xmlns:itunes`, `xmlns:ttm` (§2) — cosmetic |
| 10 | **`<p>` attribute order** `begin end ttm:agent itunes:key` | `begin end itunes:key ttm:agent` (§5) — cosmetic |

Notes on using this table:

- **Items 1–8 are substantive**; 9–10 are cosmetic and only worth
  touching if the goal is a byte-level match with Apple's style.
- **Timing Style B is *not* a deviation.** Earlier revisions of this
  document listed the editor's always-padded `MM:SS.mmm` output as an
  AMLL quirk. It isn't — an official file (`#icanteven`) uses the same
  style (§9). Leave it alone.
- **Item 5 is destructive and unrecoverable.** If a file has been round-
  tripped through the AMLL editor, its `itunes:songPart` labels are
  simply gone; they must be re-derived from the song structure by ear,
  not guessed. Warn the user about this rather than silently inventing
  section labels.
- The AMLL editor's **line-synced** output (`amll_edited_ttml/line.ttml`)
  is actually conformant — it keeps `itunes:timing`, `xml:lang`, and
  `<translations/>`, and declares no stray namespaces. The deviations
  concentrate in span-synced output.
- **AMLL does not inherently drop translations.** It supports authoring
  them; the provided span-synced samples simply have none. Their missing
  `<translations>` container is evidence only about those files, not proof
  that translation content was deleted. Preserve any translation or
  transliteration track found in AMLL output.
- These are observations from three sample files, not a spec of the
  editor. A different AMLL version may deviate differently — when
  handling an unfamiliar file, check it against §2–§11 directly rather
  than assuming this list is exhaustive.

---

## 13. Builder-only sample index

**Agents using this skill should rely on §§1–12 and §14, not on these
files.** Open samples only when maintaining the skill, regression-testing
a parser or generator, or investigating a genuinely undocumented shape.
If an ordinary TTML task appears to require sample inspection, improve
this reference afterward so the same lookup is unnecessary next time.

| Path | What it demonstrates |
|---|---|
| `official_ttml_samples/no_timing/Better In Pieces - StaJe.ttml` | Untimed `itunes:timing="None"`: plain `<body>`, `<div>`, and `<p>` with no timing attributes; manual scrolling; typographic apostrophes |
| `official_ttml_samples/line/9 to 5 (feat. khodi) - Lucidrari.ttml` | Line sync, Style C timing, no `itunes:key`, no `songPart`, no agents, single `<div>` for the whole song, `xml:lang` disagreeing with the lyric language |
| `official_ttml_samples/line/How Long - Charlie Puth.ttml` | Line sync, Style A timing, `itunes:key` on every `<p>`, `songPart` on `<div>`s, no agents, raw `"` in text |
| `official_ttml_samples/line/#icanteven … - The Neighbourhood.ttml` | **Line sync *with* agents** — `xmlns:ttm`, a `<ttm:agent>` carrying a `<ttm:name>`, `ttm:agent` on every `<p>`; Style B timing with stripped trailing zeros |
| `official_ttml_samples/line/Not So Bad … - Rae Sremmurd.ttml` | Line sync with two self-closing person agents, `ttm:agent` assignments, song parts, and parenthetical background-vocal candidates |
| `official_ttml_samples/word_syllable/10:35 - Tiesto & Tate McRae.ttml` | Single agent, mixed word/syllable granularity, 7 x-bg parts |
| `official_ttml_samples/word_syllable/APT. - ROSE & Bruno Mars.ttml` | Subtitle translations plus complete per-word `ko-Latn` romanization; transliteration spans exactly reuse lyric timings |
| `official_ttml_samples/word_syllable/Luther - Kendrick Lamar.ttml` | Four agents inc. `group`/`other`, `ttm:agent` on `<body>`, **80 multi-word spans** (§7), incidental double spaces |
| `official_ttml_samples/word_syllable/OMG - NewJeans.ttml` | Subtitle translations, automatically-created per-word romanization, optional spatial `<audio>` metadata, and leading x-bg lines |
| `official_ttml_samples/word_syllable/Popular … - The Weeknd & Madonna.ttml` | Five agents inc. `v3`, heaviest syllable splitting (186 zero-space joins), 22 x-bg parts |
| `official_ttml_samples/word_syllable/You - Regard, Troye Sivan & Tate McRae.ttml` | Four agents, `ttm:agent` on `<body>`, 21 x-bg parts |
| `amll_edited_ttml/line.ttml` | AMLL line output — conformant |
| `amll_edited_ttml/word.ttml` | AMLL word output — missing `itunes:timing` **and** `xml:lang`, `&apos;` escaping |
| `amll_edited_ttml/syllable.ttml` | AMLL syllable output — missing `xml:lang`, x-bg wrapper with `begin`/`end`, Style B timing |

These files are evidence and regression fixtures, not runtime
documentation for agents performing ordinary TTML work.

---

## 14. Quick "don't get it wrong" checklist

Before handing back any edited, generated, or converted TTML file:

- [ ] The file still parses as well-formed XML.
- [ ] The number of `<p>` elements is unchanged (unless the task was
      explicitly to add or remove lines).
- [ ] Every attribute originally present on `<body>`, `<div>`, and `<p>`
      is preserved exactly unless the task required changing it. For
      `itunes:timing="None"`, confirm timing attributes were not invented.
- [ ] `itunes:timing` and `xml:lang` are present on `<tt>`, with
      `itunes:timing` being exactly `"None"`, `"Line"`, or `"Word"` and
      matching both content and timing presence (§1–§2).
- [ ] `xmlns:ttm` is declared if and only if something in the file uses
      the `ttm:` prefix — including on line-synced files with agents.
- [ ] No `xmlns:tts` or `xmlns:amll` declarations were introduced.
- [ ] Any `<ttm:name>` inside a `<ttm:agent>` is preserved, and an
      agent's open-tag form was not collapsed to self-closing.
- [ ] In span-synced content, space appears **only** between separate timed tokens, **never**
      between spans that form one word — and existing spacing (including
      any incidental double spaces) is preserved byte-for-byte.
- [ ] Multi-word spans (§7) were left intact, not split apart.
- [ ] `itunes:songPart` values, if present, are from the known set
      (§4) and still on `<div>`, not `<p>`.
- [ ] Every `ttm:agent` referenced on `<body>`, `<div>`, or `<p>` is
      declared in `<head>`.
- [ ] `ttm:role="x-bg"` spans are preserved, structurally intact, in
      their original leading/trailing position, and — for
      Apple-conformant output — still free of `begin`/`end` on the wrapper.
- [ ] Text content escaping matches the file's existing convention (raw
      `'` for Apple files), with entities neither corrupted, double-
      escaped, nor decoded into raw `<`/`&`.
- [ ] `<translations>`, `<transliterations>`, optional `<audio>`,
      `leadingSilence`, `<songwriters>`, and the rest of `<head>` are
      untouched unless the task required changing them. Every metadata
      `<text for="L…">` still resolves to an existing `itunes:key`.
- [ ] For timed files, the existing timing-format style (§9) is matched,
      not replaced with a different one. For `"None"`, no timestamps or
      `dur` were fabricated.
