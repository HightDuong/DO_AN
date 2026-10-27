"""Trích xuất văn bản từ PDF bằng PyMuPDF và chia chunk theo token.

- Mỗi khối văn bản giữ đúng `page_number` (bắt đầu từ 1) và `section` đang hiệu lực.
- `section` lấy từ mục lục (bookmark) của PDF nếu có; nếu không, nhận diện tiêu đề
  theo cỡ chữ / chữ đậm / mẫu đánh số ("Chương 2", "2.1 ...").
- Chunk 500-800 token, overlap 80-120 token, không cắt chunk vắt qua hai mục khác nhau,
  ưu tiên cắt ở ranh giới đoạn rồi mới đến ranh giới câu.
- Nội dung PDF chỉ là dữ liệu: không diễn giải hay thực thi gì từ văn bản trích xuất.
"""
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from functools import lru_cache

import pymupdf
import tiktoken

from app.config import settings


class PDFExtractionError(Exception):
    """PDF hỏng, có mật khẩu, quá dài hoặc không có lớp văn bản."""


@dataclass
class TextBlock:
    text: str
    page_number: int
    section: str | None
    is_heading: bool = False


@dataclass
class Chunk:
    chunk_index: int
    content: str
    page_number: int
    section: str | None
    token_count: int


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    # Gemini không có tokenizer offline, dùng o200k_base để ước lượng (xử lý tiếng Việt khá sát).
    # 800 token theo ước lượng này vẫn nằm xa giới hạn 2048 token đầu vào của model embedding.
    return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text, disallowed_special=()))


# ---------------------------------------------------------------------------
# Trích xuất
# ---------------------------------------------------------------------------

_TEXT_FLAGS = (pymupdf.TEXTFLAGS_DICT | pymupdf.TEXT_DEHYPHENATE) & ~pymupdf.TEXT_PRESERVE_IMAGES
_BOLD_FLAG = 16
_MARGIN_RATIO = 0.07  # khối nằm trong 7% trên/dưới trang được coi là header/footer tiềm năng
_MAX_SECTION_LEN = 200

_CHAPTER_PATTERN = re.compile(r"^(chương|phần|bài|chapter|part|lesson|unit)\s+([\dIVXLC]+)\b", re.IGNORECASE)
_NUMBERED_PATTERN = re.compile(r"^(\d+(\.\d+)*\.?|[IVXLC]+\.|[A-Z]\.)\s+\S")
_PAGE_NUMBER_PATTERN = re.compile(r"^(trang|page)?\s*[-–]?\s*\d{1,4}\s*[-–]?$", re.IGNORECASE)
_TOC_DOT_LEADER_PATTERN = re.compile(r"\.{4,}\s*\d{1,4}\s*$")  # "... Tên mục ..........  12" (dòng mục lục)
_NON_ASCII_PATTERN = re.compile(r"[^\x00-\x7f]")  # ký tự có dấu tiếng Việt
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class _RawBlock:
    page_number: int
    text: str
    font_size: float
    bold: bool
    line_count: int
    in_margin: bool


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)  # PDF tiếng Việt hay tách dấu thành ký tự tổ hợp
    text = _CONTROL_CHARS.sub("", text)  # PostgreSQL TEXT không chấp nhận \x00
    return re.sub(r"\s+", " ", text).strip()


def _norm_key(text: str) -> str:
    return re.sub(r"\W+", "", text.casefold())


def _read_raw_blocks(doc: pymupdf.Document) -> list[_RawBlock]:
    raw: list[_RawBlock] = []
    for page in doc:
        height = page.rect.height or 1
        for block in page.get_text("dict", flags=_TEXT_FLAGS, sort=True)["blocks"]:
            if block.get("type") != 0:
                continue
            lines, sizes = [], Counter()
            bold_chars = total_chars = 0
            for line in block["lines"]:
                line_text = "".join(span["text"] for span in line["spans"]).strip()
                if line_text:
                    lines.append(line_text)
                for span in line["spans"]:
                    n = len(span["text"].strip())
                    if not n:
                        continue
                    sizes[round(span["size"], 1)] += n
                    total_chars += n
                    if span["flags"] & _BOLD_FLAG:
                        bold_chars += n
            text = _clean(" ".join(lines))
            if not text:
                continue
            y0, y1 = block["bbox"][1], block["bbox"][3]
            raw.append(
                _RawBlock(
                    page_number=page.number + 1,
                    text=text,
                    font_size=sizes.most_common(1)[0][0],
                    bold=bold_chars >= 0.8 * total_chars,
                    line_count=len(lines),
                    in_margin=y1 < height * _MARGIN_RATIO or y0 > height * (1 - _MARGIN_RATIO),
                )
            )
    return raw


def _drop_headers_footers(raw: list[_RawBlock], page_count: int) -> list[_RawBlock]:
    """Bỏ số trang và header/footer lặp lại ở lề trên/dưới."""
    repeated = Counter(
        re.sub(r"\d+", "", _norm_key(b.text)) for b in raw if b.in_margin
    )
    threshold = max(3, page_count // 5)
    kept = []
    for b in raw:
        if b.in_margin and (
            _PAGE_NUMBER_PATTERN.match(b.text)
            or repeated[re.sub(r"\d+", "", _norm_key(b.text))] >= threshold
        ):
            continue
        kept.append(b)
    return kept


def _body_font_size(raw: list[_RawBlock]) -> float:
    weights = Counter()
    for b in raw:
        weights[b.font_size] += len(b.text)
    return weights.most_common(1)[0][0]


def _looks_like_heading(b: _RawBlock, body_size: float) -> bool:
    if len(b.text) > 150 or b.line_count > 3 or b.text.endswith((",", ";")):
        return False
    if _TOC_DOT_LEADER_PATTERN.search(b.text):
        return False  # dòng trong trang Mục lục, không phải tiêu đề thật
    if _CHAPTER_PATTERN.match(b.text):
        return True
    if b.font_size >= body_size * 1.15:
        return True
    if b.bold and _NUMBERED_PATTERN.match(b.text):
        return True
    # Toàn chữ hoa + in đậm nhưng cỡ chữ như văn bản thường: chỉ coi là tiêu đề nếu có dấu
    # tiếng Việt, để không nhận nhầm dòng lệnh SQL/code ví dụ (ví dụ "SELECT * FROM EMP").
    return bool(b.bold and b.text.isupper() and _NON_ASCII_PATTERN.search(b.text))


def _sections_from_headings(raw: list[_RawBlock]) -> list[TextBlock]:
    """Không có mục lục: nhận diện tiêu đề bằng heuristic, ghép dạng "Chương > Mục"."""
    body_size = _body_font_size(raw)
    chapter: str | None = None
    sub: str | None = None
    prev_was_chapter = False
    blocks: list[TextBlock] = []
    for b in raw:
        is_heading = _looks_like_heading(b, body_size)
        if is_heading:
            if _CHAPTER_PATTERN.match(b.text):
                chapter, sub, prev_was_chapter = b.text, None, True
            elif prev_was_chapter and not _NUMBERED_PATTERN.match(b.text):
                # "CHƯƠNG 2" rồi dòng tên chương "MÔ HÌNH QUAN HỆ" tách thành hai khối
                chapter = f"{chapter}: {b.text}"
                prev_was_chapter = False
            else:
                sub, prev_was_chapter = b.text, False
        else:
            prev_was_chapter = False
        section = " > ".join(p for p in (chapter, sub) if p) or None
        blocks.append(TextBlock(b.text, b.page_number, _truncate(section), is_heading))
    return blocks


def _sections_from_toc(raw: list[_RawBlock], toc: list) -> list[TextBlock]:
    """Có mục lục: gán section theo bookmark, đánh dấu khối khớp tên mục là tiêu đề."""
    by_page: dict[int, list[tuple[int, str]]] = {}
    for level, title, page in toc:
        title = _clean(title)
        if page >= 1 and title:
            by_page.setdefault(page, []).append((level, title))

    path: list[str] = []  # path[i] = tiêu đề cấp i+1

    def enter(level: int, title: str) -> None:
        del path[level - 1:]
        path.extend([""] * (level - 1 - len(path)))
        path.append(title)

    def current() -> str | None:
        return _truncate(" > ".join(p for p in path if p) or None)

    # Bookmark ở các trang trước trang có chữ đầu tiên (bìa, trang trắng) vẫn phải có hiệu lực.
    first_page = raw[0].page_number if raw else 1
    for page in sorted(p for p in by_page if p < first_page):
        for level, title in by_page.pop(page):
            enter(level, title)

    blocks: list[TextBlock] = []
    page_no = 0
    pending: list[tuple[int, str]] = []
    for b in raw:
        if b.page_number != page_no:
            for level, title in pending:  # mục không tìm thấy dòng tiêu đề trên trang trước
                enter(level, title)
            for skipped in range(page_no + 1, b.page_number):  # trang không có chữ
                for level, title in by_page.get(skipped, []):
                    enter(level, title)
            page_no = b.page_number
            pending = list(by_page.get(page_no, []))

        key = _norm_key(b.text)
        is_heading = False
        for i, (level, title) in enumerate(pending):
            tkey = _norm_key(title)
            if tkey and (key.startswith(tkey[:60]) or (len(key) >= 8 and tkey.startswith(key))):
                for lv, t in pending[: i + 1]:
                    enter(lv, t)
                pending = pending[i + 1:]
                is_heading = True
                break
        blocks.append(TextBlock(b.text, b.page_number, current(), is_heading))
    return blocks


def _truncate(section: str | None) -> str | None:
    if section and len(section) > _MAX_SECTION_LEN:
        return section[: _MAX_SECTION_LEN - 1] + "…"
    return section


def count_pages(pdf_bytes: bytes) -> int | None:
    """Số trang của PDF; None nếu không mở được (lỗi sẽ được báo ở bước trích xuất)."""
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            return doc.page_count
    except Exception:
        return None


def extract_blocks(pdf_bytes: bytes) -> list[TextBlock]:
    """Đọc PDF, trả về các khối văn bản theo thứ tự đọc kèm số trang và mục."""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PDFExtractionError("File không phải PDF hợp lệ hoặc đã bị hỏng.") from exc

    with doc:
        if doc.needs_pass:
            raise PDFExtractionError("PDF được bảo vệ bằng mật khẩu.")
        if doc.page_count == 0:
            raise PDFExtractionError("PDF không có trang nào.")
        if doc.page_count > settings.max_pdf_pages:
            raise PDFExtractionError(
                f"PDF có {doc.page_count} trang, vượt giới hạn {settings.max_pdf_pages} trang."
            )
        try:
            raw = _read_raw_blocks(doc)
            toc = doc.get_toc(simple=True)
        except Exception as exc:
            raise PDFExtractionError("Không đọc được nội dung PDF.") from exc
        page_count = doc.page_count

    raw = _drop_headers_footers(raw, page_count)
    if sum(len(b.text) for b in raw) < 200:
        raise PDFExtractionError(
            "PDF không có lớp văn bản trích xuất được (có thể là bản scan). Hệ thống chưa hỗ trợ OCR."
        )
    return _sections_from_toc(raw, toc) if toc else _sections_from_headings(raw)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…;:])\s+(?=\S)")


@dataclass
class _Unit:
    text: str
    tokens: int
    page_number: int
    section: str | None
    block_id: int
    is_heading: bool


def _split_words(text: str, limit: int) -> list[str]:
    """Cắt một câu quá dài thành các đoạn <= limit token theo ranh giới từ."""
    pieces, current, current_tokens = [], [], 0
    for word in text.split():
        t = count_tokens(" " + word)
        if current and current_tokens + t > limit:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(word)
        current_tokens += t
    if current:
        pieces.append(" ".join(current))
    return pieces


def _tail_words(text: str, limit: int) -> str:
    """Lấy phần cuối của văn bản, tối đa `limit` token, theo ranh giới từ."""
    words, total = [], 0
    for word in reversed(text.split()):
        t = count_tokens(" " + word)
        if total + t > limit:
            break
        words.append(word)
        total += t
    return " ".join(reversed(words))


def _to_units(blocks: list[TextBlock], unit_limit: int) -> list[_Unit]:
    units = []
    for block_id, block in enumerate(blocks):
        parts = [block.text] if block.is_heading else _SENTENCE_SPLIT.split(block.text)
        for part in parts:
            tokens = count_tokens(part)
            pieces = [part] if tokens <= unit_limit else _split_words(part, unit_limit)
            for piece in pieces:
                units.append(
                    _Unit(
                        text=piece,
                        tokens=tokens if piece is part else count_tokens(piece),
                        page_number=block.page_number,
                        section=block.section,
                        block_id=block_id,
                        is_heading=block.is_heading,
                    )
                )
    return units


def _overlap_tail(units: list[_Unit], min_tokens: int, max_tokens: int) -> list[_Unit]:
    tail: list[_Unit] = []
    total = 0
    for unit in reversed(units):
        if total + unit.tokens <= max_tokens:
            tail.insert(0, unit)
            total += unit.tokens
            continue
        if total < min_tokens:
            piece = _tail_words(unit.text, max_tokens - total)
            if piece:
                tail.insert(0, replace(unit, text=piece, tokens=count_tokens(piece)))
        break
    return tail


def _render(units: list[_Unit]) -> str:
    out: list[str] = []
    prev: _Unit | None = None
    for unit in units:
        if prev is not None:
            same_block = unit.block_id == prev.block_id and not unit.is_heading
            out.append(" " if same_block else "\n\n")
        out.append(unit.text)
        prev = unit
    return "".join(out)


def chunk_blocks(blocks: list[TextBlock]) -> list[Chunk]:
    """Gom các khối thành chunk 500-800 token, overlap 80-120 token."""
    min_t = settings.chunk_min_tokens
    max_t = settings.chunk_max_tokens
    ov_min = settings.chunk_overlap_min_tokens
    ov_max = settings.chunk_overlap_max_tokens

    units = _to_units(blocks, unit_limit=max_t - ov_max)
    block_tokens: Counter = Counter()
    for unit in units:
        block_tokens[unit.block_id] += unit.tokens

    chunks: list[Chunk] = []
    current: list[_Unit] = []
    carried = 0  # số unit đầu `current` là overlap từ chunk trước
    current_tokens = 0

    def has_body() -> bool:
        return any(not u.is_heading for u in current[carried:])

    def flush(keep_overlap: bool) -> None:
        nonlocal current, carried, current_tokens
        if not has_body():
            return  # chỉ có tiêu đề: giữ lại để ghép vào phần nội dung phía sau
        body = current[carried:]
        content = _render(current)
        chunks.append(
            Chunk(
                chunk_index=len(chunks),
                content=content,
                page_number=body[0].page_number,
                section=next(u.section for u in body if not u.is_heading),
                token_count=count_tokens(content),
            )
        )
        current = _overlap_tail(current, ov_min, ov_max) if keep_overlap else []
        carried = len(current)
        current_tokens = sum(u.tokens for u in current)

    for unit in units:
        if current and has_body() and unit.section != current[-1].section:
            flush(keep_overlap=False)  # không để chunk vắt qua hai mục
        if not has_body() and carried:
            # chưa có nội dung mới mà đã sang mục khác: bỏ overlap của mục cũ
            if unit.section != current[0].section:
                current, carried = current[carried:], 0
                current_tokens = sum(u.tokens for u in current)

        if has_body():
            starts_block = unit.block_id != current[-1].block_id
            if current_tokens + unit.tokens > max_t:
                flush(keep_overlap=True)
            elif starts_block and current_tokens >= min_t and current_tokens + block_tokens[unit.block_id] > max_t:
                flush(keep_overlap=True)  # ưu tiên cắt ở ranh giới đoạn

        current.append(unit)
        current_tokens += unit.tokens

    flush(keep_overlap=False)
    return chunks
