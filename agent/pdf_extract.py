"""
agent/pdf_extract.py — MINIMAL STDLIB PDF TEXT EXTRACTOR
==========================================================

The rest of this repo is deliberately zero-dependency (only `ollama` is a
real package). Rather than pull in PyPDF2/pdfplumber for the PDF-upload demo,
this is a small, transparent extractor good enough for typical text-based
PDFs (reports, articles, notes — including ones made via a browser's "Print
to PDF", which is the single most common real-world case).

What it does, step by step (mirrors what we show in the UI trace):
  1. Find every PDF stream (`stream ... endstream`) and Flate-decompress it
     when possible (most PDF content is zlib-compressed).
  2. Collect any ToUnicode CMaps (`beginbfchar`/`beginbfrange` blocks) — these
     map a font's internal glyph codes (CIDs) back to real Unicode text.
     Browsers/LibreOffice/Word almost always subset+embed fonts with
     Identity-H encoding, so the content stream's text operators contain raw
     2-byte glyph IDs, NOT ASCII — without this step you'd extract garbage.
  3. ALSO best-effort walk the real object graph (page -> /Resources ->
     /Font -> font object -> /ToUnicode) to resolve a PER-FONT CID map, not
     just one merged table — two different embedded fonts can reuse the same
     CID for different characters, and a single merged table silently picks
     whichever font's mapping was parsed last. When this resolves, the
     content-stream parser switches CMaps on every `/FontName size Tf`
     operator; when it can't (unusual PDF structure, size caps, etc.) we
     transparently fall back to the merged table from step 2 — never worse
     than before, sometimes more accurate.
  4. Parse each content stream's text-showing operators (Tj / TJ inside
     BT...ET blocks), handling BOTH literal strings `(abc)` (older/simpler
     PDFs, single-byte fonts) and hex strings `<0024004A...>` (CID fonts) —
     decoding hex strings via the per-font CMap (preferred) or the merged
     CMap from step 2 (fallback).

Performance note: a PDF's biggest streams are almost always embedded images
or font programs, not actual page text — and raw binary data can easily
contain the literal bytes "Tj"/"BT" by pure chance. Running a backtracking
regex meant for text operators over megabytes of that noise is what makes a
naive version of this slow (measured: 30+ seconds on an 8-page, 3.5MB PDF
with embedded images). So we skip any stream over MAX_STREAM_BYTES outright
(real per-page content streams are essentially never that large) and require
BT/Tj/TJ to appear as whitespace-delimited tokens, not bare substrings. The
object-graph walk for per-font resolution uses plain `bytes.find()` for its
obj->endobj boundaries (not a backtracking regex spanning megabytes) for the
same reason, and is capped by object count and wrapped in a blanket
try/except — any failure there just means we fall back to the merged map,
never a crash and never a regression versus the old behavior.

Limitations (explicitly, not hidden): per-font resolution assumes generation
number 0 on indirect references (true for virtually all real-world PDFs),
resolves `/Contents` as a single reference or array of references on the
page object itself (not inherited `/Resources` from a parent `/Pages` node —
rare in practice for simple documents), and is skipped outright above
MAX_OBJECTS_FOR_FONT_RESOLUTION objects or MAX_STREAM_BYTES per stream. When
it can't resolve, behavior is identical to the old merged-CMap-only version.
Scanned/image-only PDFs (no text layer) still extract nothing, by design —
that's a different problem (OCR).
"""
from __future__ import annotations
import re
import zlib

# Real per-page content streams are rarely this big even for text-dense
# pages; anything larger is almost certainly an embedded image or font
# program, and parsing those for text operators is both pointless and (on
# multi-MB binary data) can take tens of seconds due to regex backtracking.
MAX_STREAM_BYTES = 400_000

# Require BT/Tj/TJ as whitespace-delimited tokens rather than bare substring
# checks — raw binary (images, fonts) can contain these two/three-byte
# sequences by pure chance, which is what makes a naive substring check a
# performance trap on image-heavy PDFs.
_LOOKS_LIKE_CONTENT_STREAM = re.compile(rb"(?:^|[\s>\]])(?:BT|Tj|TJ)(?:[\s\\(<]|$)")

# Per-font resolution walks every object in the file; cap it so a pathological
# (or just unusually large) PDF can't turn this best-effort enhancement into a
# slow scan. Above this, extraction still works — just via the merged CMap.
MAX_OBJECTS_FOR_FONT_RESOLUTION = 3_000

# How far past an "N G obj" header to look for its matching "endobj" using a
# plain substring search (not a backtracking regex) — generous enough for a
# multi-MB embedded image/font object, small enough to bound worst-case work.
_MAX_OBJ_LOOKAHEAD = 3_000_000

_OBJ_HEADER = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")


def extract_text(pdf_bytes: bytes) -> str:
    """Pull plain text out of a PDF's content streams. Returns '' on
    anything unparseable rather than raising, so the caller can react."""
    cmap = _build_cid_to_unicode_map(pdf_bytes)
    font_maps_by_stream = _build_per_font_maps(pdf_bytes)  # best-effort, may be {}

    text_parts = []
    # Grab every `stream ... endstream` blob directly rather than trying to
    # parse each object's `<<...>>` dictionary first — PDF dictionaries
    # nest (e.g. `/Resources << ... >>` inside the page object's own
    # `<<...>>`), and a naive non-greedy regex on `<<(.*?)>>` stops at the
    # FIRST `>>` it finds (the nested dict's close), silently pairing the
    # wrong bytes with the wrong stream. Decompressing blind and checking
    # the RESULT for text operators sidesteps that whole class of bug.
    for m in re.finditer(rb"[^a-zA-Z]stream\r?\n(.*?)endstream", pdf_bytes, re.DOTALL):
        raw = m.group(1)
        if len(raw) > MAX_STREAM_BYTES * 4:  # cheap pre-check before decompressing at all
            continue
        try:
            stream = zlib.decompress(raw)
        except zlib.error:
            stream = raw  # not Flate-compressed — use as-is
        if len(stream) > MAX_STREAM_BYTES:
            continue  # almost certainly an image/font blob, not page text
        if not _LOOKS_LIKE_CONTENT_STREAM.search(stream):
            continue
        # Exact-content lookup: if the object-graph walk resolved this exact
        # stream's fonts, use them; otherwise font_maps is None and the
        # content-stream parser falls back to the merged cmap for every CID.
        font_maps = font_maps_by_stream.get(stream)
        text_parts.append(_text_from_content_stream(stream, cmap, font_maps))

    return "\n".join(p for p in text_parts if p).strip()


# ──────────────────────────────────────────────────────────────────────────
# Merged ToUnicode CMap (the original, always-on fallback)
# ──────────────────────────────────────────────────────────────────────────

def _build_cid_to_unicode_map(pdf_bytes: bytes) -> dict[int, str]:
    """Merge every embedded ToUnicode CMap in the document into one {cid: char}
    table. Used as the fallback whenever per-font resolution doesn't apply —
    correct whenever a document uses one font (or several fonts whose CIDs
    don't collide), which covers most simple documents."""
    table: dict[int, str] = {}
    for m in re.finditer(rb"[^a-zA-Z]stream\r?\n(.*?)endstream", pdf_bytes, re.DOTALL):
        raw = m.group(1)
        try:
            stream = zlib.decompress(raw)
        except zlib.error:
            stream = raw
        if b"beginbfchar" not in stream and b"beginbfrange" not in stream:
            continue
        table.update(_parse_cmap_stream(stream))
    return table


def _parse_cmap_stream(stream: bytes) -> dict[int, str]:
    """Parse one decompressed ToUnicode CMap stream's bfchar/bfrange blocks.

    CMap syntax (inside `begincmap ... endcmap`):
      beginbfchar
        <0024> <0041>        # one glyph code -> one Unicode codepoint
      endbfchar
      beginbfrange
        <0024> <0030> <0041>  # a contiguous range, Unicode increments too
      endbfrange
    """
    table: dict[int, str] = {}
    for block in re.finditer(rb"beginbfchar(.*?)endbfchar", stream, re.DOTALL):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block.group(1)):
            table[int(src, 16)] = _hex_to_unicode(dst)
    for block in re.finditer(rb"beginbfrange(.*?)endbfrange", stream, re.DOTALL):
        for lo, hi, dst in re.findall(
            rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block.group(1)
        ):
            lo_i, hi_i, dst_i = int(lo, 16), int(hi, 16), int(dst, 16)
            for offset, cid in enumerate(range(lo_i, hi_i + 1)):
                table[cid] = chr(dst_i + offset)
    return table


def _hex_to_unicode(hex_bytes: bytes) -> str:
    """A ToUnicode destination can be a UTF-16BE codepoint (one or more
    16-bit units); decode it properly rather than assuming 2 bytes = 1 char."""
    raw = bytes.fromhex(hex_bytes.decode("ascii"))
    try:
        return raw.decode("utf-16-be")
    except UnicodeDecodeError:
        return ""


# ──────────────────────────────────────────────────────────────────────────
# Per-font CMap resolution (best-effort object-graph walk)
# ──────────────────────────────────────────────────────────────────────────

def _parse_objects(pdf_bytes: bytes) -> dict[int, tuple[bytes, bytes | None]]:
    """Best-effort map of {object_number: (dict_bytes, raw_stream_bytes_or_None)}.

    Uses bytes.find() for the obj->endobj boundary (a plain substring scan,
    not a backtracking regex) specifically so a multi-MB embedded image/font
    object inside one "obj...endobj" can't reintroduce the slowdown class
    fixed in the main extractor. If "endobj" isn't found within a bounded
    lookahead, that object is skipped (safe: callers treat missing objects
    as "can't resolve", falling back to the merged CMap)."""
    objects: dict[int, tuple[bytes, bytes | None]] = {}
    for m in _OBJ_HEADER.finditer(pdf_bytes):
        num = int(m.group(1))
        start = m.end()
        window_end = min(len(pdf_bytes), start + _MAX_OBJ_LOOKAHEAD)
        end = pdf_bytes.find(b"endobj", start, window_end)
        if end == -1:
            continue
        body = pdf_bytes[start:end]
        stream_at = body.find(b"stream")
        if stream_at == -1:
            objects[num] = (body, None)
            continue
        payload_start = stream_at + len(b"stream")
        if body[payload_start:payload_start + 2] == b"\r\n":
            payload_start += 2
        elif body[payload_start:payload_start + 1] == b"\n":
            payload_start += 1
        else:
            # "stream" wasn't followed by a line break -- probably matched
            # part of another word (e.g. a /Name containing "stream"), not
            # the real keyword. Treat as dict-only.
            objects[num] = (body[:stream_at], None)
            continue
        # First "endstream" after the payload start -- matches the same
        # first-match semantics the main extractor's blind scan uses, so a
        # stream's bytes are identical however it's reached (this is what
        # lets the main loop look streams up by exact decompressed content).
        stream_end = body.find(b"endstream", payload_start)
        stream_bytes = body[payload_start:stream_end] if stream_end != -1 else body[payload_start:]
        objects[num] = (body[:stream_at], stream_bytes)
    return objects


def _find_key_ref(dict_text: bytes, key: str) -> int | None:
    """Find an indirect reference `/Key N G R` in a dict and return N
    (generation number G is ignored -- virtually always 0 in practice)."""
    m = re.search(rb"/" + re.escape(key.encode()) + rb"\s+(\d+)\s+\d+\s+R", dict_text)
    return int(m.group(1)) if m else None


def _find_key_inline_dict(dict_text: bytes, key: str) -> bytes | None:
    """Find an inline dict value `/Key << ... >>` and return its raw bytes.

    Uses bracket-depth counting rather than a non-greedy regex: PDF dicts
    nest (e.g. `/Resources << /Font << ... >> >>`), and `/Key\\s*<<(.*?)>>`
    would stop at the FIRST `>>` -- the inner dict's close -- truncating the
    outer one. This is the exact same nested-dict trap documented elsewhere
    in this module, hit again here one level up."""
    m = re.search(rb"/" + re.escape(key.encode()) + rb"\s*<<", dict_text)
    if not m:
        return None
    start = m.end()  # just past the opening "<<"
    depth, i, n = 1, start, len(dict_text)
    while i < n and depth > 0:
        if dict_text[i:i + 2] == b"<<":
            depth += 1
            i += 2
        elif dict_text[i:i + 2] == b">>":
            depth -= 1
            i += 2
        else:
            i += 1
    if depth != 0:
        return None  # unbalanced brackets -- bail out safely rather than guess
    return dict_text[start:i - 2]


def _find_page_for_content(objects: dict, content_num: int) -> int | None:
    """Which object's /Contents references this content-stream object?
    Best-effort substring check rather than a precise array-aware parse --
    good enough because a false match just means we might attach the wrong
    (or no) font map to one stream, which only affects per-font accuracy,
    never crashes or breaks the merged-CMap fallback path."""
    needle = f"{content_num} 0 R".encode()
    for num, (dict_text, _stream) in objects.items():
        if b"/Contents" in dict_text and needle in dict_text:
            return num
    return None


def _get_resources_dict(objects: dict, page_num: int) -> bytes | None:
    dict_text, _ = objects.get(page_num, (b"", None))
    ref = _find_key_ref(dict_text, "Resources")
    if ref is not None and ref in objects:
        res_dict_text, _ = objects[ref]
        return res_dict_text
    return _find_key_inline_dict(dict_text, "Resources")


def _get_font_dict(objects: dict, resources_dict_text: bytes | None) -> bytes | None:
    if not resources_dict_text:
        return None
    ref = _find_key_ref(resources_dict_text, "Font")
    if ref is not None and ref in objects:
        font_dict_text, _ = objects[ref]
        return font_dict_text
    return _find_key_inline_dict(resources_dict_text, "Font")


_FONT_ENTRY = re.compile(rb"/(\w+)\s+(\d+)\s+\d+\s+R")


def _parse_font_name_map(font_dict_text: bytes | None) -> dict[str, int]:
    """`<< /F1 5 0 R /F2 6 0 R >>` -> {"F1": 5, "F2": 6}."""
    if not font_dict_text:
        return {}
    return {name.decode(errors="ignore"): int(num)
            for name, num in _FONT_ENTRY.findall(font_dict_text)}


def _resolve_font_cmap(objects: dict, font_obj_num: int) -> dict[int, str] | None:
    """Font object -> its own /ToUnicode CMap (or None if it doesn't have one,
    e.g. a non-embedded standard font, which this extractor can't help with
    anyway since there's no embedded glyph data to decode)."""
    dict_text, _ = objects.get(font_obj_num, (b"", None))
    tu_ref = _find_key_ref(dict_text, "ToUnicode")
    if tu_ref is None or tu_ref not in objects:
        return None
    _, stream_bytes = objects[tu_ref]
    if not stream_bytes:
        return None
    try:
        decompressed = zlib.decompress(stream_bytes)
    except zlib.error:
        decompressed = stream_bytes
    cmap = _parse_cmap_stream(decompressed)
    return cmap or None


def _build_per_font_maps(pdf_bytes: bytes) -> dict[bytes, dict[str, dict[int, str]]]:
    """Best-effort: for each content-stream object, resolve exactly which
    embedded font (by its content-stream-local name, e.g. /F1) backs each
    Tf-selected font, via the real object graph (page -> /Resources ->
    /Font -> font object -> /ToUnicode) instead of merging every CMap in
    the document into one table.

    Returns {decompressed_stream_bytes: {font_name: {cid: char}}}, keyed by
    the stream's own decompressed content so the main extraction loop (which
    finds streams via a separate, already-proven-safe blind regex) can look
    up a precise per-font map for exactly the bytes it's already parsing —
    zero coupling between the two code paths. Any failure anywhere in this
    function (malformed refs, missing objects, too many objects, oversized
    streams) is swallowed: the caller just gets {} or a partial result and
    falls back to the merged CMap for whatever it can't resolve. This can
    never make extraction worse than before, only more accurate when it works.
    """
    try:
        objects = _parse_objects(pdf_bytes)
    except Exception:
        return {}
    if not objects or len(objects) > MAX_OBJECTS_FOR_FONT_RESOLUTION:
        return {}

    result: dict[bytes, dict[str, dict[int, str]]] = {}
    for num, (_dict_text, stream_bytes) in objects.items():
        if not stream_bytes or len(stream_bytes) > MAX_STREAM_BYTES * 4:
            continue
        try:
            decompressed = zlib.decompress(stream_bytes)
        except zlib.error:
            decompressed = stream_bytes
        if len(decompressed) > MAX_STREAM_BYTES:
            continue
        if not _LOOKS_LIKE_CONTENT_STREAM.search(decompressed):
            continue
        try:
            page_num = _find_page_for_content(objects, num)
            if page_num is None:
                continue
            resources = _get_resources_dict(objects, page_num)
            font_dict_text = _get_font_dict(objects, resources)
            font_names = _parse_font_name_map(font_dict_text)
            font_maps = {}
            for fname, fnum in font_names.items():
                fcmap = _resolve_font_cmap(objects, fnum)
                if fcmap:
                    font_maps[fname] = fcmap
            if font_maps:
                result[decompressed] = font_maps
        except Exception:
            continue  # this one object's resolution failed -- skip it, not fatal
    return result


# ──────────────────────────────────────────────────────────────────────────
# Content-stream parsing (text-showing operators)
# ──────────────────────────────────────────────────────────────────────────

# A single ordered scan for font selection (Tf) and text-showing (Tj/TJ)
# operators, so we can track "which font is currently selected" correctly —
# Tf and Tj/TJ must be processed in the order they actually appear in the
# stream, not as two separate passes that lose that interleaving.
_TOKEN = re.compile(
    rb"/(?P<font>[\w#]+)\s+[\d.]+\s+Tf"
    rb"|(?P<tj>\(.*?\)|<[0-9A-Fa-f\s]*>)\s*Tj"
    rb"|\[(?P<arr>.*?)\]\s*TJ",
    re.DOTALL,
)
_ARRAY_PIECE = re.compile(rb"\(.*?\)|<[0-9A-Fa-f\s]*>", re.DOTALL)


def _text_from_content_stream(
    stream: bytes,
    cmap: dict[int, str],
    font_maps: dict[str, dict[int, str]] | None = None,
) -> str:
    """Parse the PDF content-stream mini-language for text operators.

    (text) Tj                       -> literal string, single-byte chars
    <0024004A> Tj                   -> hex string, 2-byte CIDs (needs a cmap)
    [(a) -250 (b)] TJ / [<..> ..] TJ -> array form, mixed literal/hex pieces
    /F1 12 Tf                       -> selects font F1 for subsequent text —
                                        if font_maps has F1's own CMap, hex
                                        strings after this use it instead of
                                        the merged fallback `cmap`.
    Positioning/graphics-state operators are irrelevant to recovering words
    and are ignored.
    """
    font_maps = font_maps or {}
    out = []
    current_cmap = cmap  # default: the merged, document-wide fallback table

    def handle_piece(piece: bytes):
        piece = piece.strip()
        if piece.startswith(b"(") and piece.endswith(b")"):
            out.append(_decode_literal_string(piece[1:-1]))
        elif piece.startswith(b"<") and piece.endswith(b">"):
            out.append(_decode_hex_string(piece[1:-1], current_cmap))

    for m in _TOKEN.finditer(stream):
        font = m.group("font")
        if font is not None:
            fname = font.decode(errors="ignore")
            current_cmap = font_maps.get(fname, cmap)
            continue
        tj = m.group("tj")
        if tj is not None:
            handle_piece(tj)
            out.append(" ")  # each Tj is typically its own line/run of text
            continue
        arr = m.group("arr")
        if arr is not None:
            for piece in _ARRAY_PIECE.finditer(arr):
                handle_piece(piece.group(0))
            out.append(" ")  # one TJ array is one visual line

    return "".join(out)


def _decode_literal_string(raw: bytes) -> str:
    """Undo the handful of backslash escapes PDF literal strings use."""
    s = raw.decode("latin-1", errors="replace")
    s = s.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return s


def _decode_hex_string(hex_bytes: bytes, cmap: dict[int, str]) -> str:
    """Decode a CID-encoded hex string (2 bytes per glyph) via the given
    ToUnicode map (per-font if resolved, else the merged fallback). A CID
    with no mapping is dropped rather than guessed at — better an honest
    gap than a wrong character."""
    hex_str = re.sub(rb"\s+", b"", hex_bytes).decode("ascii", errors="ignore")
    if len(hex_str) % 4 != 0:
        hex_str = hex_str[: len(hex_str) - (len(hex_str) % 4)]
    chars = []
    for i in range(0, len(hex_str), 4):
        cid = int(hex_str[i : i + 4], 16)
        chars.append(cmap.get(cid, ""))
    return "".join(chars)
