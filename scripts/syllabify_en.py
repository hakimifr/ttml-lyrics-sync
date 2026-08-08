#!/usr/bin/env python3
"""
English syllable splitter for Apple Music TTML lyric files.

Takes a span-synced (itunes:timing="Word") file and splits each
whole-word <span> into N consecutive <span> elements, one per syllable,
with NO space between them - while leaving the single space between
separate words untouched, per the core rule in
references/ttml-format.md section 8.

Timing: real syllable timing has to come from listening to the vocal
performance, so this script evenly divides each original word's
begin/end duration across its syllables. That produces valid,
non-overlapping PLACEHOLDER timestamps - not real sync. Always tell the
user a manual listen-through pass is expected afterward.

Usage:
    python3 syllabify_en.py <input.ttml> <output.ttml>
    python3 syllabify_en.py <input.ttml> --check   # validate only, no write

What it deliberately does NOT touch:
  - Line-synced <p> elements (plain text, no spans) - passed through.
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

This is a best-effort TEXTUAL heuristic, not a phonetic/dictionary
lookup. Known limitations (disclose these to the user every time this
script is used):
  - It cannot know how a word is actually sung; natural syllable count
    and emphasis often differ from print/dictionary hyphenation.
  - Morpheme-boundary ambiguity (whether a vowel pair is a true
    diphthong or two separate morphemes) can't be resolved from text
    alone.
  - Only English is implemented and verified. Do not use it on lyrics
    in other languages.
  - Always recommend a listen-through pass to fix both syllable
    boundaries and timing after running this.
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
    "ee", "oo", "ea", "oa", "ai", "ay", "oy", "oi", "ou", "ow",
    "ie", "ei", "ey", "au", "aw", "ue", "eu", "oe",
}

# XML entities are collapsed to single opaque placeholder characters so
# their letters are never mistaken for word letters (format reference
# section 11). Apple's own files use raw ' and " instead of entities, so
# both paths have to work.
ENT_QUOT, ENT_APOS, ENT_AMP = "\x01", "\x02", "\x03"
ENTITIES = (("&quot;", ENT_QUOT), ("&apos;", ENT_APOS), ("&amp;", ENT_AMP))

# Both a raw apostrophe and an escaped one count as an apostrophe.
APOSTROPHES = ("'", ENT_APOS)

# Smallest syllable duration worth emitting. Below this, splitting would
# produce timestamps that round to zero length, so the word is left whole.
MIN_SYLLABLE_SECONDS = 0.001


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


def syllabify_core(core):
    """core: a pure A-Za-z run. Returns a list of syllable strings."""
    if not core:
        return [core]

    vowel_idx = [i for i in range(len(core)) if is_vowel(core, i)]
    if len(vowel_idx) <= 1:
        return [core]

    # Silent trailing "e" (blame, there, gone, promise) - drop it as a
    # nucleus rather than let it form its own syllable.
    if len(core) >= 2 and core[-1].lower() == "e" and not is_vowel(core, len(core) - 2):
        last_i = len(core) - 1
        if last_i in vowel_idx and len(vowel_idx) > 1:
            vowel_idx.remove(last_i)
    # Silent "e" before past-tense "-ed" (involved, happened) - unless
    # preceded by t/d, where "-ed" IS its own syllable (wanted, needed).
    elif len(core) >= 3 and core[-2:].lower() == "ed" and not is_vowel(core, len(core) - 3) \
            and core[-3].lower() not in ("t", "d"):
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
        cluster = core[v1 + 1:v2]
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
    if len(mid) > 2 and mid[-2:].lower() == "in" \
            and post[:1] in APOSTROPHES:
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

SPAN_TAG_RE = re.compile(r'<span(\s[^>]*)?>|</span>', re.DOTALL)
P_RE = re.compile(r'<p(\s[^>]*)?>(.*?)</p>', re.DOTALL)
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
            children_stack[-1].append(("text", s[pos:m.start()]))
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
    return re.sub(r'(\s%s=")[^"]*(")' % name,
                  lambda m: m.group(1) + value + m.group(2), attrs, count=1)


class Stats(object):
    def __init__(self):
        self.words_split = 0
        self.syllables_made = 0
        self.multiword_spans = 0
        self.too_short_to_split = 0
        self.leaf_spans = 0
        self.bg_wrappers = 0


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
            return match.group(0)  # line-synced <p>: leave alone
        return "<p" + attrs + ">" + render(
            transform_nodes(parse_nodes(inner), style, stats)) + "</p>"

    return P_RE.sub(process_p, text), style, stats


# --------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------

TAG_RE = re.compile(r"<[^>]+>")


def text_content(s):
    """All text outside tags, entity-normalized - must be identical
    before and after, since splitting only moves tag boundaries."""
    body = TAG_RE.sub("", s)
    for ent, ph in ENTITIES:
        body = body.replace(ent, ph)
    return body


def validate(before, after):
    """Returns a list of problem strings; empty means all checks pass."""
    problems = []

    try:
        ET.fromstring(after)
    except ET.ParseError as exc:
        problems.append("output is not well-formed XML: %s" % exc)

    n_before = len(re.findall(r"<p[\s>]", before))
    n_after = len(re.findall(r"<p[\s>]", after))
    if n_before != n_after:
        problems.append("<p> count changed: %d -> %d" % (n_before, n_after))

    if text_content(before) != text_content(after):
        problems.append("lyric text content changed - characters were "
                        "added, dropped or reordered")

    for name, pat in (("x-bg wrapper", r'ttm:role="x-bg"'),
                      ("itunes:key", r"itunes:key="),
                      ("ttm:agent", r"ttm:agent=")):
        a, b = len(re.findall(pat, before)), len(re.findall(pat, after))
        if a != b:
            problems.append("%s count changed: %d -> %d" % (name, a, b))

    n_span_before = len(re.findall(r"<span[\s>]", before))
    n_span_after = len(re.findall(r"<span[\s>]", after))
    if n_span_after < n_span_before:
        problems.append("spans were lost: %d -> %d" % (n_span_before, n_span_after))

    return problems


def syllabify_file(in_path, out_path=None):
    with open(in_path, "r", encoding="utf-8") as f:
        original = f.read()

    warnings = []

    # English only. xml:lang is a weak signal - one official sample has
    # Malay lyrics tagged "en" - so this catches the obvious case only,
    # and the caller still has to judge from the lyrics themselves.
    lang = re.search(r'xml:lang="([^"]*)"', original)
    if lang and not lang.group(1).lower().startswith("en"):
        warnings.append(
            'file is tagged xml:lang="%s" but this splitter implements '
            "English only. Do not use the output without checking the "
            "lyrics are actually English." % lang.group(1))

    timing = re.search(r'itunes:timing="([^"]*)"', original)
    if timing is None:
        warnings.append(
            "input has no itunes:timing attribute - Apple always sets it "
            "(see format reference section 2 and the AMLL deviation table "
            "in section 12). Consider restoring itunes:timing=\"Word\".")
    elif timing.group(1) == "Line":
        warnings.append(
            'input declares itunes:timing="Line"; a line-synced file has '
            "no word spans to split. Nothing will change.")

    new_text, style, stats = syllabify_text(original)
    problems = validate(original, new_text)

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
    print("word spans examined:   %d" % stats.leaf_spans)
    print("words split:           %d  (into %d syllable spans)"
          % (stats.words_split, stats.syllables_made))
    print("left whole:            %d multi-word span(s), %d too short to split"
          % (stats.multiword_spans, stats.too_short_to_split))
    print("x-bg wrappers kept:    %d" % stats.bg_wrappers)

    for w in warnings:
        print("WARNING: %s" % w)

    if problems:
        for p in problems:
            print("FAILED: %s" % p)
        print("No output written.")
        return 2

    print("validation: OK (well-formed, <p> count, text content, spans, "
          "x-bg, keys and agents all preserved)")
    if out_path:
        print("Wrote %s" % out_path)
    print("NOTE: syllable timings are evenly-divided placeholders, not real "
          "sync. Both the split points and the timings need a "
          "listen-through pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
