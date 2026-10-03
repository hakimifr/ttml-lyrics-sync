#!/usr/bin/env python3
"""
English syllable splitter for Apple Music TTML lyric files.

Converts either sync form to syllable-level spans:
  - line-synced: splits each plain-text <p> on whitespace, syllabifies
    every token, moves balanced parenthesized segments into a final x-bg
    wrapper, and distributes the line duration evenly across all
    resulting syllables;
  - span-synced: splits each whole-word <span> into N consecutive
    syllable spans within that span's existing duration.

In both paths there is NO space between syllables of one word, while
the original whitespace between separate words is preserved, per the
core rule in references/ttml-format.md section 8.

Untimed files (`itunes:timing="None"`) are rejected: they contain no
line, word, or song-duration timings from which valid spans could be
derived. Supply or author timing data first; never infer it from line
order alone.

Files with `<transliterations>` are also rejected. Per-word romanization
mirrors the body spans' exact timings, so changing only the body would
silently break the alignment between the two tracks.

Timing: real syllable timing has to come from listening to the vocal
performance, so this script evenly divides each original word's
begin/end duration across its syllables. That produces valid,
non-overlapping PLACEHOLDER timestamps - not real sync. Always tell the
user a manual listen-through pass is expected afterward.

Usage:
    python3 syllabify_en.py <input.ttml> <output.ttml>
    python3 syllabify_en.py <input.ttml> --check   # validate only, no write

What it deliberately does NOT touch:
  - Multi-word spans, e.g. a single span reading "do it" (format
    reference section 7). These are a deliberate authoring choice for
    fast passages; splitting them would misrepresent the timing. They
    are counted and reported instead.
  - ttm:role="x-bg" wrapper spans. The wrapper is preserved exactly as
    found, including whether it carries begin/end; only the word spans
    *inside* it are syllabified.
  - Inter-span whitespace of any kind, including the incidental double
    spaces that occur in real Apple files. Whitespace is structural
    here and is reproduced byte-for-byte.
  - The file's timing format. The existing convention (bare seconds /
    MM:SS / HH:MM:SS - format reference section 9) is detected and
    matched for every timestamp written.

Line-sync background heuristic:
  - Balanced parenthetical segments are treated as likely background
    vocals, moved into one final <span ttm:role="x-bg"> wrapper, and
    retain their parentheses.
  - A line made entirely of parenthetical text is NOT converted to x-bg;
    x-bg must be attached to a main-vocal line. Such a line remains
    ordinary main-vocal span content for manual review during timing.
  - The generated x-bg wrapper is preceded by one literal space whenever
    it is emitted. This is the structural separator between the main
    line and the background-vocal part.
  - This is a heuristic: parenthesized text is not guaranteed to be sung
    background. Review the generated output before presenting it.

This is a best-effort TEXTUAL heuristic, not a phonetic/dictionary
lookup. Known limitations (disclose these to the user every time this
script is used):
  - It cannot know how a word is actually sung; natural syllable count
    and emphasis often differ from print/dictionary hyphenation.
  - Morpheme-boundary ambiguity (whether a vowel pair is a true
    diphthong or two separate morphemes) can't be resolved from text
    alone. Known compound seams are handled by an explicit list
    (MORPHEME_SUFFIXES) rather than a general rule, so the list covers
    what's been seen so far, not every possible word.
  - Only English is implemented and verified. Do not use it on lyrics
    in other languages.
  - Always recommend a listen-through pass to fix both syllable
    boundaries and timing after running this.

Silent-"e" handling, which is where most bad splits come from. All three
cases drop the "e" as a syllable nucleus:
  - word-final:        blame, there, gone, promise
  - before "-s":       times, names, makes  (NOT sibilants, where "-es"
                       is a real syllable: chan-ces, ro-ses, wa-shes)
  - before "-ed":      involved, happened  (NOT after t/d, where "-ed"
                       is a real syllable: wan-ted, nee-ded)
A silent "e" mid-word at a compound seam ("something") is handled by
splitting the compound first, so each part hits the word-final case.
"""

import re
import sys
import xml.etree.ElementTree as ET

VOWEL_LETTERS = set("aeiouAEIOU")

# Consonant pairs treated as one indivisible unit that moves together to
# the following syllable's onset. Splitting these produces syllables no
# singer can read - "not|hing", "teac|her", "was|hing" - because each
# pair spells a single sound. "ck" is deliberately absent: it is one
# sound too, but "poc|ket" matches standard hyphenation better than
# "po|cket", and both halves stay pronounceable either way.
CONSONANT_DIGRAPHS = {"ng", "ny", "sy", "kh", "gh", "th", "sh", "ch", "ph", "wh"}

# Vowel pairs representing ONE vowel sound, which must not be split into
# separate syllables ("creep", "feel", "boy").
VOWEL_DIGRAPHS = {
    "ee",
    "oo",
    "ea",
    "oa",
    "ai",
    "ay",
    "oy",
    "oi",
    "ou",
    "ow",
    "ie",
    "ei",
    "ey",
    "au",
    "aw",
    "ue",
    "eu",
    "oe",
}

# XML entities are collapsed to single opaque placeholder characters so
# their letters are never mistaken for word letters (format reference
# section 11). Apple's own files use raw ' and " instead of entities, so
# both paths have to work.
ENT_QUOT, ENT_APOS, ENT_AMP = "\x01", "\x02", "\x03"
ENTITIES = (("&quot;", ENT_QUOT), ("&apos;", ENT_APOS), ("&amp;", ENT_AMP))

# Morpheme boundaries: compound second-elements and consonant-initial
# suffixes, longest first. Splitting here before applying the vowel rules
# fixes words whose silent "e" sits mid-word at the seam of a compound -
# "something" would otherwise come out "so-me-thing" instead of
# "some-thing", because the silent-e rule below only looks at the END of
# a word. Splitting first lets each part ("some", "thing") run through
# that rule on its own, which already handles it correctly. Same repair
# for hope-ful, love-ly, care-less, move-ment, nine-teen.
#
# Kept deliberately short and high-confidence. Every entry has to be a
# real morpheme seam a singer would phrase across, since a wrong entry
# mis-splits every word that happens to end in those letters.
MORPHEME_SUFFIXES = (
    "bodies",
    "body",
    "thing",
    "things",
    "where",
    "times",
    "time",
    "light",
    "night",
    "teen",
    "ment",
    "less",
    "ness",
    "some",
    "work",
    "ful",
    "one",
    "day",
    "days",
    "how",
    "ly",
)

# Apple's text uses both ASCII and typographic apostrophes; AMLL may use
# &apos;, represented internally by ENT_APOS while text is analysed.
APOSTROPHES = ("'", "’", ENT_APOS)

# Smallest syllable duration worth emitting. Below this, splitting would
# produce timestamps that round to zero length, so the word is left whole.
MIN_SYLLABLE_SECONDS = 0.000


def encode(s):
    for ent, ph in ENTITIES:
        s = s.replace(ent, ph)
    return s


def decode(s):
    for ent, ph in ENTITIES:
        s = s.replace(ph, ent)
    return s


def is_alpha(c):
    return ("a" <= c <= "z") or ("A" <= c <= "Z")


def is_vowel(core, i):
    c = core[i]
    if c in VOWEL_LETTERS:
        return True
    # 'y' is a vowel except as the very first letter of the word
    # (yeah, you -> consonant; shady, only -> vowel)
    if c in ("y", "Y") and i > 0:
        return True
    return False


def split_morphemes(core):
    """Split a letter run at known morpheme seams, longest match first.
    Returns a list of parts (just [core] when nothing matches). Recurses
    on the head so "everything" -> ["every", "thing"] and multi-seam
    words still come apart."""
    low = core.lower()
    for suf in MORPHEME_SUFFIXES:
        if len(low) > len(suf) + 1 and low.endswith(suf):
            head = core[: -len(suf)]
            # The head has to be able to stand alone as a syllable, i.e.
            # contain a vowel. Guards against "thing" itself, or heads
            # like "str" that are only a cluster.
            if any(is_vowel(head, i) for i in range(len(head))):
                return split_morphemes(head) + [core[-len(suf) :]]
    return [core]


def syllabify_core(core):
    """core: a pure A-Za-z run. Returns a list of syllable strings."""
    if not core:
        return [core]

    parts = split_morphemes(core)
    if len(parts) > 1:
        out = []
        for p in parts:
            out.extend(syllabify_run(p))
        return out
    return syllabify_run(core)


def syllabify_run(core):
    """Apply the vowel/consonant rules to a single morpheme."""
    if not core:
        return [core]

    vowel_idx = [i for i in range(len(core)) if is_vowel(core, i)]
    if len(vowel_idx) <= 1:
        return [core]

    # Silent trailing "e" (blame, there, gone, promise) - drop it as a
    # nucleus rather than let it form its own syllable.
    #
    # The "or ...y" clause covers "-ye" words: bye, dye, rye, goodbye. A
    # noninitial y normally counts as a vowel (shady, only), which would
    # make the final e look like a second nucleus and split "good-by-e".
    # For a FINAL e specifically, a preceding y behaves as the consonant
    # frame, so the e is silent just as it is in "blame".
    if len(core) >= 2 and core[-1].lower() == "e" and (not is_vowel(core, len(core) - 2) or core[-2].lower() == "y"):
        last_i = len(core) - 1
        if last_i in vowel_idx and len(vowel_idx) > 1:
            vowel_idx.remove(last_i)
    # Silent "e" before a plural / 3rd-person "-s" (times, names, smiles,
    # makes). Without this the silent e keeps its nucleus and produces an
    # unsingable tail: "ti-mes", "na-mes", "ma-kes".
    #
    # The exception is sibilants, where "-es" genuinely IS a spoken
    # syllable: chan-ces, voi-ces, ro-ses, wa-shes, boun-ces. Those are
    # detected by the consonant before the "e" and left alone.
    elif (
        len(core) >= 4
        and core[-1].lower() == "s"
        and core[-2].lower() == "e"
        and (not is_vowel(core, len(core) - 3) or core[-3].lower() == "y")
        and core[-3].lower() not in ("c", "s", "g", "x", "z")
        and core[-4:-2].lower() not in ("ch", "sh")
    ):
        e_i = len(core) - 2
        if e_i in vowel_idx and len(vowel_idx) > 1:
            vowel_idx.remove(e_i)
    # Silent "e" before past-tense "-ed" (involved, happened) - unless
    # preceded by t/d, where "-ed" IS its own syllable (wanted, needed).
    elif (
        len(core) >= 3
        and core[-2:].lower() == "ed"
        and not is_vowel(core, len(core) - 3)
        and core[-3].lower() not in ("t", "d")
    ):
        e_i = len(core) - 2
        if e_i in vowel_idx and len(vowel_idx) > 1:
            vowel_idx.remove(e_i)

    if len(vowel_idx) <= 1:
        return [core]

    syllables = []
    syl_start = 0
    k = 0
    while k < len(vowel_idx) - 1:
        v1 = vowel_idx[k]
        v2 = vowel_idx[k + 1]
        cluster = core[v1 + 1 : v2]
        n = len(cluster)
        if n == 0:
            pair = (core[v1] + core[v2]).lower()
            if pair in VOWEL_DIGRAPHS:
                k += 1
                continue  # same nucleus, no syllable boundary here
            split_at = v2
        elif n == 1:
            split_at = v1 + 1
        elif n == 2:
            split_at = v1 + 1 if cluster.lower() in CONSONANT_DIGRAPHS else v1 + 2
        else:
            split_at = v1 + 3 if cluster[:2].lower() in CONSONANT_DIGRAPHS else v1 + 1 + (n - 2)
        syllables.append(core[syl_start:split_at])
        syl_start = split_at
        k += 1
    syllables.append(core[syl_start:])
    return syllables


def _peel(enc):
    """Split an encoded token into (leading non-letters, middle, trailing
    non-letters), where middle starts and ends with a letter."""
    i = 0
    while i < len(enc) and not is_alpha(enc[i]):
        i += 1
    j = len(enc)
    while j > i and not is_alpha(enc[j - 1]):
        j -= 1
    return enc[:i], enc[i:j], enc[j:]


def syllabify_word(word):
    """word: the exact text content of one <span>. Returns a list of
    strings to become consecutive <span>s, or a 1-element list to leave
    the token un-split."""
    enc = encode(word)
    pre, mid, post = _peel(enc)
    if not mid:
        return [word]

    # Informal "...in'" ending (creepin', goin', callin', feelin').
    # Always its own trailing syllable: a generic vowel-adjacency read of
    # "oin" would treat it as one diphthong nucleus and refuse to split.
    # Fires on both a raw apostrophe and an escaped one.
    if len(mid) > 2 and mid[-2:].lower() == "in" and post[:1] in APOSTROPHES:
        base, suffix = mid[:-2], mid[-2:] + post
        syls = syllabify_core(base) if base else []
        syls = [s for s in syls if s]
        if syls:
            syls[0] = pre + syls[0]
            return [decode(s) for s in syls + [suffix]]
        return [decode(pre + base + suffix)]

    # Contraction or possessive with an apostrophe inside the word
    # (don't, heaven's, you're). Syllabify the part before the last
    # apostrophe and carry the tail on the final syllable.
    apos_pos = max(mid.rfind(a) for a in APOSTROPHES)
    if apos_pos >= 0:
        base, tail = mid[:apos_pos], mid[apos_pos:]
        # Anything more exotic than one internal apostrophe: leave alone.
        if not base or any(not is_alpha(c) for c in base):
            return [word]
        syls = syllabify_core(base)
        if len(syls) <= 1:
            return [word]
        syls[0] = pre + syls[0]
        syls[-1] = syls[-1] + tail + post
        return [decode(s) for s in syls]

    # Plain token: the middle must be a clean letter run to be analysed.
    # Anything else (digits or symbols mid-token, non-ASCII letters) is
    # left whole rather than risk mangling it.
    if any(not is_alpha(c) for c in mid):
        return [word]

    syls = syllabify_core(mid)
    if len(syls) <= 1:
        return [word]
    syls[0] = pre + syls[0]
    syls[-1] = syls[-1] + post
    return [decode(s) for s in syls]


# --------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------

TIME_ATTR_RE = re.compile(r'\b(?:begin|end|dur)="([^"]*)"')


def parse_time(t):
    """Accepts SS.mmm, M:SS.mmm, MM:SS.mmm and HH:MM:SS.mmm."""
    total = 0.0
    for part in t.strip().split(":"):
        total = total * 60 + float(part)
    return total


def detect_time_style(text):
    """Determine the file's existing timestamp convention (format
    reference section 9) so new timestamps match it.

      'hms'  - HH:MM:SS.mmm everywhere          (style C)
      'mmss' - MM:SS.mmm everywhere, zero-padded (style B)
      'bare' - bare seconds under a minute, M:SS.mmm at and above one
               minute (style A - Apple's dominant convention)
    """
    values = [v for v in TIME_ATTR_RE.findall(text) if v.strip()]
    if not values:
        return "bare"
    if any(v.count(":") >= 2 for v in values):
        return "hms"
    if all(":" in v for v in values):
        return "mmss"
    return "bare"


def format_time(total_seconds, style="bare"):
    ms = int(round(max(0.0, total_seconds) * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s = rem / 1000.0
    if style == "hms":
        return "%02d:%02d:%06.3f" % (h, m, s)
    if style == "mmss":
        return "%02d:%06.3f" % (h * 60 + m, s)
    minutes = h * 60 + m
    return "%d:%06.3f" % (minutes, s) if minutes > 0 else "%.3f" % s


# --------------------------------------------------------------------
# Structural parsing
#
# The <p> body is parsed into a small tree of text and span nodes rather
# than scanned with a flat findall. A flat scan cannot see the nesting of
# an x-bg wrapper, silently drops any span whose attributes don't match
# the expected shape, and loses the exact inter-span whitespace on
# re-join - all three of which corrupt the file.
# --------------------------------------------------------------------

SPAN_TAG_RE = re.compile(r"<span(\s[^>]*)?>|</span>", re.DOTALL)
P_RE = re.compile(r"<p(\s[^>]*)?>(.*?)</p>", re.DOTALL)
ATTR_RE = re.compile(r'(\s%s=")([^"]*)(")')


def parse_nodes(s):
    """Parse span markup into a tree of ('text', str) and
    ('span', attrs_str, children) nodes. Unrecognized or unbalanced
    markup is preserved verbatim as text."""
    children_stack = [[]]
    attrs_stack = []
    pos = 0
    for m in SPAN_TAG_RE.finditer(s):
        if m.start() > pos:
            children_stack[-1].append(("text", s[pos : m.start()]))
        pos = m.end()
        if m.group().startswith("</"):
            if len(children_stack) > 1:
                kids = children_stack.pop()
                children_stack[-1].append(("span", attrs_stack.pop(), kids))
            else:
                children_stack[-1].append(("text", m.group()))
        else:
            children_stack.append([])
            attrs_stack.append(m.group(1) or "")
    if pos < len(s):
        children_stack[-1].append(("text", s[pos:]))
    # Unclosed spans: fold back to literal text so nothing is lost.
    while len(children_stack) > 1:
        kids = children_stack.pop()
        children_stack[-1].append(("text", "<span" + attrs_stack.pop() + ">"))
        children_stack[-1].extend(kids)
    return children_stack[0]


def render(nodes):
    out = []
    for node in nodes:
        if node[0] == "text":
            out.append(node[1])
        else:
            out.append("<span" + node[1] + ">" + render(node[2]) + "</span>")
    return "".join(out)


def get_attr(attrs, name):
    m = re.search(r'\s%s="([^"]*)"' % name, attrs)
    return m.group(1) if m else None


def set_attr(attrs, name, value):
    return re.sub(r'(\s%s=")[^"]*(")' % name, lambda m: m.group(1) + value + m.group(2), attrs, count=1)


class Stats:
    def __init__(self):
        self.lines_converted = 0
        self.line_tokens = 0
        self.line_syllables = 0
        self.unconvertible_lines = 0
        self.words_split = 0
        self.syllables_made = 0
        self.multiword_spans = 0
        self.too_short_to_split = 0
        self.leaf_spans = 0
        self.bg_wrappers = 0
        self.generated_bg_wrappers = 0
        self.parenthetical_segments = 0
        self.parenthetical_syllables = 0
        self.unbalanced_parenthetical_lines = 0


def parenthetical_ranges(text):
    """Return (top-level parenthetical ranges, balanced).

    Each range is (start, end, text), with end exclusive. Nested
    parentheses stay inside the outer group. Any unmatched parenthesis
    disables the heuristic for the whole line.
    """
    stack = []
    groups = []
    for i, char in enumerate(text):
        if char == "(":
            stack.append(i)
        elif char == ")":
            if not stack:
                return [], False
            start = stack.pop()
            if not stack:
                groups.append((start, i + 1, text[start : i + 1]))

    if stack:
        return [], False
    return groups, True


def extract_parentheticals(text):
    """Return (main text, parenthetical groups, ranges, balanced)."""
    ranges, balanced = parenthetical_ranges(text)
    if not balanced:
        return text, [], [], False

    # Empty parentheses contain no candidate vocal. Leave the entire line
    # ordinary instead of creating a meaningless x-bg wrapper.
    if any(not group[1:-1].strip() for _, _, group in ranges):
        return text, [], [], True

    main_parts = []
    cursor = 0
    for start, end, _ in ranges:
        main_parts.append(text[cursor:start])
        # If a parenthetical was directly between two alphanumeric runs,
        # retain a word boundary after moving it. Do not insert a space
        # before punctuation: Hello(yeah), world -> Hello, world.
        if start > 0 and end < len(text) and text[start - 1].isalnum() and text[end].isalnum():
            main_parts.append(" ")
        cursor = end
    main_parts.append(text[cursor:])
    main = "".join(main_parts)
    if ranges:
        # Removing a parenthetical can leave whitespace on both sides.
        # Normalize only this converted line; ungrouped line conversion
        # continues to preserve whitespace exactly.
        main = re.sub(r"\s+", " ", main).strip()
    return main, [group for _, _, group in ranges], ranges, True


def token_records(text):
    """Return (whitespace-preserving chunks, token records).

    Each record contains the original token's syllables and receives
    placeholder timestamps later.
    """
    chunks = re.split(r"(\s+)", text)
    records = []
    for chunk in chunks:
        if chunk and not chunk.isspace():
            records.append({"text": chunk, "syllables": syllabify_word(chunk), "timings": []})
    return chunks, records


def render_token_records(chunks, records, style):
    """Render token records back into spans while retaining whitespace."""
    out = []
    record_index = 0
    for chunk in chunks:
        if not chunk or chunk.isspace():
            out.append(chunk)
            continue
        record = records[record_index]
        record_index += 1
        for syllable, (begin, end) in zip(record["syllables"], record["timings"]):
            out.append(
                '<span begin="%s" end="%s">%s</span>' % (format_time(begin, style), format_time(end, style), syllable)
            )
    return "".join(out)


def ensure_ttm_namespace(text):
    """Add Apple's ttm namespace when generated x-bg markup needs it."""
    if re.search(r'\bxmlns:ttm="[^"]*"', text):
        return text
    ttm = ' xmlns:ttm="http://www.w3.org/ns/ttml#metadata"'
    updated, count = re.subn(r'(<tt\b[^>]*\bxmlns:itunes="[^"]*")', r"\1" + ttm, text, count=1)
    if count:
        return updated
    return re.sub(r"<tt\b", "<tt" + ttm, text, count=1)


def transform_line_p(attrs, inner, style, stats):
    """Convert one plain-text line-synced <p> directly to syllable spans.

    Whitespace chunks are retained verbatim. The line duration is divided
    evenly across all emitted syllables; words that the heuristic leaves
    unsplit count as one syllable span. This is placeholder timing only.
    """
    begin, end = get_attr(attrs, "begin"), get_attr(attrs, "end")
    if begin is None or end is None:
        stats.unconvertible_lines += 1
        return "<p" + attrs + ">" + inner + "</p>"

    main_text, parenthetical_groups, ranges, balanced = extract_parentheticals(inner)
    if not balanced:
        stats.unbalanced_parenthetical_lines += 1
        main_text, parenthetical_groups, ranges = inner, [], []

    # x-bg is attached to a main-vocal line. A parenthetical-only line is
    # kept as ordinary main-vocal content for manual review. Punctuation
    # outside the parentheses does not by itself count as a main vocal.
    has_main_vocal = any(char.isalnum() or char == "*" for char in main_text)
    generate_bg = bool(parenthetical_groups and has_main_vocal)
    if not generate_bg:
        main_text, parenthetical_groups, ranges = inner, [], []

    main_chunks, main_records = token_records(main_text)
    bg_chunks, _ = token_records(" ".join(parenthetical_groups))

    # Build records in original lyric order so placeholder timing follows
    # the source sequence even though x-bg is rendered at the end of <p>.
    ordered_records = []
    cursor = 0
    if generate_bg:
        for start, range_end, group in ranges:
            fragment = inner[cursor:start]
            _, fragment_records = token_records(fragment)
            ordered_records.extend(("main", record) for record in fragment_records)
            _, group_records = token_records(group)
            ordered_records.extend(("bg", record) for record in group_records)
            cursor = range_end
        _, fragment_records = token_records(inner[cursor:])
        ordered_records.extend(("main", record) for record in fragment_records)
    else:
        ordered_records.extend(("main", record) for record in main_records)

    total_syllables = sum(len(record["syllables"]) for _, record in ordered_records)

    if total_syllables == 0:
        stats.unconvertible_lines += 1
        return "<p" + attrs + ">" + inner + "</p>"

    b, e = parse_time(begin), parse_time(end)
    step = (e - b) / total_syllables
    t0 = b
    emitted = 0
    for kind, record in ordered_records:
        record["timings"] = []
        stats.line_tokens += 1
        if kind == "bg":
            stats.parenthetical_syllables += len(record["syllables"])
        for _ in record["syllables"]:
            emitted += 1
            t1 = e if emitted == total_syllables else t0 + step
            record["timings"].append((t0, t1))
            t0 = t1

    main_ordered = [record for kind, record in ordered_records if kind == "main"]
    bg_ordered = [record for kind, record in ordered_records if kind == "bg"]
    main_output = render_token_records(main_chunks, main_ordered, style)
    bg_output = render_token_records(bg_chunks, bg_ordered, style)
    if generate_bg:
        stats.generated_bg_wrappers += 1
        stats.parenthetical_segments += len(parenthetical_groups)
        wrapper = '<span ttm:role="x-bg">' + bg_output + "</span>"
        # x-bg always follows a main-vocal part and has one literal
        # structural space before its opening wrapper tag.
        content = main_output + " " + wrapper
    else:
        content = main_output

    stats.lines_converted += 1
    stats.line_syllables += total_syllables
    return "<p" + attrs + ">" + content + "</p>"


def transform_nodes(nodes, style, stats):
    """Replace each leaf word span with its syllable spans. Text nodes -
    the structural whitespace - and every wrapper span are passed through
    untouched."""
    out = []
    for node in nodes:
        if node[0] == "text":
            out.append(node)
            continue

        attrs, kids = node[1], node[2]
        is_leaf = all(k[0] == "text" for k in kids)

        if not is_leaf:
            # A wrapper (x-bg, or anything else nested): keep it exactly
            # as found and recurse into its contents.
            if 'ttm:role="x-bg"' in attrs:
                stats.bg_wrappers += 1
            out.append(("span", attrs, transform_nodes(kids, style, stats)))
            continue

        text = "".join(k[1] for k in kids)
        begin, end = get_attr(attrs, "begin"), get_attr(attrs, "end")
        if begin is None or end is None:
            out.append(node)
            continue

        stats.leaf_spans += 1

        # A span holding several words is a deliberate authoring choice
        # for fast passages (format reference section 7) - leave it.
        if " " in text.strip():
            stats.multiword_spans += 1
            out.append(node)
            continue

        syls = syllabify_word(text)
        if len(syls) <= 1:
            out.append(node)
            continue

        b, e = parse_time(begin), parse_time(end)
        if (e - b) / len(syls) < MIN_SYLLABLE_SECONDS:
            stats.too_short_to_split += 1
            out.append(node)
            continue

        stats.words_split += 1
        stats.syllables_made += len(syls)
        step = (e - b) / len(syls)
        t0 = b
        for i, syl in enumerate(syls):
            t1 = e if i == len(syls) - 1 else t0 + step
            a = set_attr(attrs, "begin", format_time(t0, style))
            a = set_attr(a, "end", format_time(t1, style))
            out.append(("span", a, [("text", syl)]))
            t0 = t1
    return out


def syllabify_text(text):
    style = detect_time_style(text)
    stats = Stats()

    def process_p(match):
        attrs, inner = match.group(1) or "", match.group(2)
        if "<span" not in inner:
            return transform_line_p(attrs, inner, style, stats)
        return "<p" + attrs + ">" + render(transform_nodes(parse_nodes(inner), style, stats)) + "</p>"

    result = P_RE.sub(process_p, text)
    if stats.lines_converted:
        result = re.sub(r'(\bitunes:timing=")Line(")', r"\1Word\2", result, count=1)
    if stats.generated_bg_wrappers:
        result = ensure_ttm_namespace(result)
    return result, style, stats


# --------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------

TAG_RE = re.compile(r"<[^>]+>")
HEAD_RE = re.compile(r"<head(?:\s[^>]*)?>.*?</head>", re.DOTALL)


def text_content(s):
    """All text outside tags, entity-normalized - must be identical
    before and after, since splitting only moves tag boundaries."""
    body = TAG_RE.sub("", s)
    for ent, ph in ENTITIES:
        body = body.replace(ent, ph)
    return body


def expected_text_after_line_bg_conversion(s):
    """Canonical source text after the intentional x-bg relocation.

    For eligible line-synced <p>s, move parenthetical groups after the
    main text exactly as transform_line_p does. Tags are then stripped so
    validation can still prove no lyric characters were lost or altered.
    """

    def canonical_p(match):
        attrs, inner = match.group(1) or "", match.group(2)
        if "<span" in inner:
            return match.group(0)
        if get_attr(attrs, "begin") is None or get_attr(attrs, "end") is None:
            return match.group(0)
        main, groups, _, balanced = extract_parentheticals(inner)
        if not balanced or not groups or not main.strip():
            return match.group(0)
        return "<p" + attrs + ">" + main + " " + " ".join(groups) + "</p>"

    return text_content(P_RE.sub(canonical_p, s))


def validate(before, after, generated_bg_wrappers=0):
    """Returns a list of problem strings; empty means all checks pass."""
    problems = []

    try:
        ET.fromstring(after)
    except ET.ParseError as exc:
        problems.append("output is not well-formed XML: %s" % exc)

    head_before = HEAD_RE.search(before)
    head_after = HEAD_RE.search(after)
    if (head_before is None) != (head_after is None) or (
        head_before is not None and head_before.group(0) != head_after.group(0)
    ):
        problems.append(
            "<head> metadata changed - translations, "
            "transliterations, agents or credits were not "
            "preserved byte-for-byte"
        )

    n_before = len(re.findall(r"<p[\s>]", before))
    n_after = len(re.findall(r"<p[\s>]", after))
    if n_before != n_after:
        problems.append("<p> count changed: %d -> %d" % (n_before, n_after))

    expected_text = expected_text_after_line_bg_conversion(before) if generated_bg_wrappers else text_content(before)
    if expected_text != text_content(after):
        problems.append("lyric text content changed - characters were added, dropped or reordered")

    for name, pat in (("itunes:key", r"itunes:key="), ("ttm:agent", r"ttm:agent=")):
        a, b = len(re.findall(pat, before)), len(re.findall(pat, after))
        if a != b:
            problems.append("%s count changed: %d -> %d" % (name, a, b))

    bg_before = len(re.findall(r'ttm:role="x-bg"', before))
    bg_after = len(re.findall(r'ttm:role="x-bg"', after))
    expected_bg = bg_before + generated_bg_wrappers
    if bg_after != expected_bg:
        problems.append(
            "x-bg wrapper count changed unexpectedly: %d -> %d (expected %d)" % (bg_before, bg_after, expected_bg)
        )

    n_span_before = len(re.findall(r"<span[\s>]", before))
    n_span_after = len(re.findall(r"<span[\s>]", after))
    if n_span_after < n_span_before:
        problems.append("spans were lost: %d -> %d" % (n_span_before, n_span_after))

    return problems


def syllabify_file(in_path, out_path=None):
    with open(in_path, encoding="utf-8") as f:
        original = f.read()

    warnings = []

    if re.search(r"<transliterations(?:\s|>)", original):
        style = detect_time_style(original)
        problems = [
            "input contains a transliteration/romanization track. This "
            "splitter does not update its mirrored per-word spans, so "
            "conversion is refused to prevent lyric/romanization timing "
            "misalignment."
        ]
        return original, style, Stats(), problems, warnings

    # English only. xml:lang is a weak signal - one official sample has
    # Malay lyrics tagged "en" - so this catches the obvious case only,
    # and the caller still has to judge from the lyrics themselves.
    lang = re.search(r'xml:lang="([^"]*)"', original)
    if lang and not lang.group(1).lower().startswith("en"):
        warnings.append(
            'file is tagged xml:lang="%s" but this splitter implements '
            "English only. Do not use the output without checking the "
            "lyrics are actually English." % lang.group(1)
        )

    timing = re.search(r'itunes:timing="([^"]*)"', original)
    if timing is None:
        has_spans = bool(re.search(r"<p(?:\s[^>]*)?>.*?<span[\s>]", original, re.DOTALL))
        has_timed_lines = bool(re.search(r'<p\s[^>]*\bbegin="[^"]+"[^>]*\bend="[^"]+"', original))
        if has_spans:
            suggestion = 'Timed spans establish itunes:timing="Word".'
        elif has_timed_lines:
            suggestion = 'Timed plain-text lines establish itunes:timing="Line".'
        else:
            suggestion = (
                'The structure may be untimed ("None") or incomplete; '
                "do not guess without the intended mode or source timings."
            )
        warnings.append("input has no itunes:timing attribute - Apple always sets it. " + suggestion)
    elif timing.group(1) == "Line":
        warnings.append(
            'input declares itunes:timing="Line"; plain-text lines will '
            "be converted to syllable spans and the value changed to "
            'itunes:timing="Word".'
        )

    new_text, style, stats = syllabify_text(original)
    problems = validate(original, new_text, stats.generated_bg_wrappers)

    if timing is not None and timing.group(1) == "None":
        problems.append(
            'input declares itunes:timing="None" and contains no timing '
            "data. Timed syllable spans cannot be generated without "
            "separately authored timings."
        )
    elif timing is not None and timing.group(1) not in ("Line", "Word"):
        problems.append(
            'unsupported itunes:timing value %r; Apple uses only "None", "Line", or "Word".' % timing.group(1)
        )

    if out_path and not problems:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(new_text)

    return new_text, style, stats, problems, warnings


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip().split("\n\n")[3])
        return 1

    in_path = argv[1]
    check_only = argv[2] == "--check"
    out_path = None if check_only else argv[2]

    new_text, style, stats, problems, warnings = syllabify_file(in_path, out_path)

    print("timing style detected: %s" % style)
    print(
        "line <p>s converted:    %d  (%d token(s), %d syllable span(s))"
        % (stats.lines_converted, stats.line_tokens, stats.line_syllables)
    )
    if stats.unconvertible_lines:
        print("line <p>s left plain:   %d  (missing timing or no tokens)" % stats.unconvertible_lines)
    print("word spans examined:   %d" % stats.leaf_spans)
    print("words split:           %d  (into %d syllable spans)" % (stats.words_split, stats.syllables_made))
    print(
        "left whole:            %d multi-word span(s), %d too short to split"
        % (stats.multiword_spans, stats.too_short_to_split)
    )
    print("x-bg wrappers kept:    %d" % stats.bg_wrappers)
    print(
        "x-bg wrappers created: %d  (%d parenthetical segment(s), %d syllable span(s))"
        % (stats.generated_bg_wrappers, stats.parenthetical_segments, stats.parenthetical_syllables)
    )
    if stats.unbalanced_parenthetical_lines:
        print("parenthetical lines left ordinary: %d  (unbalanced parentheses)" % stats.unbalanced_parenthetical_lines)

    for w in warnings:
        print("WARNING: %s" % w)

    if problems:
        for p in problems:
            print("FAILED: %s" % p)
        print("No output written.")
        return 2

    print(
        "validation: OK (well-formed, <head> metadata, <p> count, text "
        "content, spans, x-bg, keys and agents all preserved)"
    )
    if out_path:
        print("Wrote %s" % out_path)
    print(
        "NOTE: syllable timings are evenly-divided placeholders, not real "
        "sync. Both the split points and the timings need a "
        "listen-through pass."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
