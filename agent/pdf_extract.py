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
  3. Parse each content stream's text-showing operators (Tj / TJ inside
     BT...ET blocks), handling BOTH literal strings `(abc)` (older/simpler
     PDFs, single-byte fonts) and hex strings `<0024004A...>` (CID fonts) —
     decoding hex strings via the CMap from step 2.

Performance note: a PDF's biggest streams are almost always embedded images
or font programs, not actual page text — and raw binary data can easily
contain the literal bytes "Tj"/"BT" by pure chance. Running a backtracking
regex meant for text operators over megabytes of that noise is what makes a
naive version of this slow (measured: 30+ seconds on an 8-page, 3.5MB PDF
with embedded images). So we skip any stream over MAX_STREAM_BYTES outright
(real per-page content streams are essentially never that large) and require
BT/Tj/TJ to appear as whitespace-delimited tokens, not bare substrings.

Limitations (explicitly, not hidden): this merges all CMaps found in the
document into one table rather than resolving per-font indirect references
through the full object graph — correct for the common case (one or a
handful of embedded fonts per document), but a from-scratch full PDF parser
would track font->CMap precisely. Scanned/image-only PDFs (no text layer)
still extract nothing, by design — that's a different problem (OCR).
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


def extract_text(pdf_bytes: bytes) -> str:
    """Pull plain text out of a PDF's content streams. Returns '' on
    anything unparseable rather than raising, so the caller can react."""
    cmap = _build_cid_to_unicode_map(pdf_bytes)

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
        text_parts.append(_text_from_content_stream(stream, cmap))

    return "\n".join(p for p in text_parts if p).strip()


def _build_cid_to_unicode_map(pdf_bytes: bytes) -> dict[int, str]:
    """Parse every embedded ToUnicode CMap into one combined {cid: char} map.

    CMap syntax (inside `begincmap ... endcmap`):
      beginbfchar
        <0024> <0041>        # one glyph code -> one Unicode codepoint
      endbfchar
      beginbfrange
        <0024> <0030> <0041>  # a contiguous range, Unicode increments too
      endbfrange
    """
    table: dict[int, str] = {}

    for m in re.finditer(rb"[^a-zA-Z]stream\r?\n(.*?)endstream", pdf_bytes, re.DOTALL):
        raw = m.group(1)
        try:
            stream = zlib.decompress(raw)
        except zlib.error:
            stream = raw
        if b"beginbfchar" not in stream and b"beginbfrange" not in stream:
            continue

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


def _text_from_content_stream(stream: bytes, cmap: dict[int, str]) -> str:
    """Parse the PDF content-stream mini-language for text operators.

    (text) Tj                       -> literal string, single-byte chars
    <0024004A> Tj                   -> hex string, 2-byte CIDs (needs cmap)
    [(a) -250 (b)] TJ / [<..> ..] TJ -> array form, mixed literal/hex pieces
    We only care about the strings; positioning/graphics-state operators are
    irrelevant to recovering the words.
    """
    out = []

    def handle_piece(piece: bytes):
        piece = piece.strip()
        if piece.startswith(b"(") and piece.endswith(b")"):
            out.append(_decode_literal_string(piece[1:-1]))
        elif piece.startswith(b"<") and piece.endswith(b">"):
            out.append(_decode_hex_string(piece[1:-1], cmap))

    # (string) Tj  or  <hex> Tj — single string followed by the Tj operator.
    # Match only well-formed literal/hex string syntax (not any '(' through
    # any ')'), or a stray '<' from an unrelated dict (e.g. `<</MCID 0>>`)
    # can get mistaken for the start of a hex string.
    for m in re.finditer(rb"(\(.*?\)|<[0-9A-Fa-f\s]*>)\s*Tj", stream, re.DOTALL):
        handle_piece(m.group(1))
        out.append(" ")  # each Tj is typically its own line/run of text

    # [ (a) n <hex> n (b) ... ] TJ — array form, strings interleaved with
    # numeric kerning adjustments we don't care about.
    for m in re.finditer(rb"\[(.*?)\]\s*TJ", stream, re.DOTALL):
        for piece in re.finditer(rb"\(.*?\)|<[0-9A-Fa-f\s]*>", m.group(1), re.DOTALL):
            handle_piece(piece.group(0))
        out.append(" ")  # one TJ array is one visual line; keep words separated

    return "".join(out)


def _decode_literal_string(raw: bytes) -> str:
    """Undo the handful of backslash escapes PDF literal strings use."""
    s = raw.decode("latin-1", errors="replace")
    s = s.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return s


def _decode_hex_string(hex_bytes: bytes, cmap: dict[int, str]) -> str:
    """Decode a CID-encoded hex string (2 bytes per glyph) via the ToUnicode
    map. A CID with no mapping is dropped rather than guessed at — better an
    honest gap than a wrong character."""
    hex_str = re.sub(rb"\s+", b"", hex_bytes).decode("ascii", errors="ignore")
    if len(hex_str) % 4 != 0:
        hex_str = hex_str[: len(hex_str) - (len(hex_str) % 4)]
    chars = []
    for i in range(0, len(hex_str), 4):
        cid = int(hex_str[i : i + 4], 16)
        chars.append(cmap.get(cid, ""))
    return "".join(chars)
