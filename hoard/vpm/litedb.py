"""Reading vcc.liteDb, where the Creator Companion (2.2 and newer) and ALCOM keep their projects and Unity editors.

A LiteDB 5 file is a run of 8 KiB pages: a header page naming each collection's page, a collection page listing its
indexes, index pages (a skip list per index) and data pages holding each document as BSON, split over blocks when
it's large. This walks a collection's _id index from its head to its tail and reads each document it points to,
as vrc-get's own LiteDB reader (vrc-get-litedb, MIT) does. It only ever reads: Hoard never writes this file, and
lists a project there by writing settings.json, which both programs copy into it themselves.

Anything that isn't as described is refused (DatabaseError) rather than guessed at: the file could be one a newer
version wrote, or a damaged one.
"""
from __future__ import annotations

import struct
from pathlib import Path

PAGE = 8192
HEADER_INFO = b"** This is a LiteDB file **"
FILE_VERSION = 8
EMPTY_PAGE = 0xFFFFFFFF
EMPTY_SLOT = 0xFF
MAX_FILE = 256 << 20          # the Creator Companion's database is a few hundred KB; far beyond that isn't one
MAX_DOCUMENTS = 100_000
MAX_DOCUMENT = 16 << 20
MAX_DEPTH = 32
INDEX, DATA, COLLECTION = 3, 4, 2


class DatabaseError(ValueError):
    """A file that isn't a LiteDB 5 database this can read."""


class _Pages:
    def __init__(self, data: bytes):
        self.data = data
        self.count = len(data) // PAGE

    def page(self, page_id: int, kind: int) -> int:
        if not 0 <= page_id < self.count:
            raise DatabaseError("a reference to a page that isn't there")
        at = page_id * PAGE
        if struct.unpack_from("<I", self.data, at)[0] != page_id or self.data[at + 4] != kind:
            raise DatabaseError("a page that isn't what it should be")
        return at

    def block(self, page_id: int, slot: int, kind: int) -> bytes:
        at = self.page(page_id, kind)
        items, highest = self.data[at + 23], self.data[at + 30]
        if items == 0 or highest == EMPTY_SLOT or slot > highest:
            raise DatabaseError("a reference to a block that isn't there")
        length, position = struct.unpack_from("<HH", self.data, at + PAGE - (slot + 1) * 4)
        footer = (highest + 1) * 4
        if length == 0 or not 32 <= position < PAGE - footer or position + length > PAGE - footer:
            raise DatabaseError("a block outside its page")
        return self.data[at + position:at + position + length]


def _address(buf: bytes, at: int) -> tuple[int, int] | None:
    page_id, slot = struct.unpack_from("<IB", buf, at)
    return None if page_id == EMPTY_PAGE and slot == EMPTY_SLOT else (page_id, slot)


def _cstring(buf: bytes, at: int) -> tuple[str, int]:
    end = buf.find(b"\x00", at)
    if end < 0:
        raise DatabaseError("a name with no end")
    return buf[at:end].decode("utf-8", "replace"), end + 1


def read_bson(buf: bytes, at: int = 0, depth: int = 0) -> tuple[dict, int]:
    """One BSON document from buf at at: (the document, where it ends). Arrays come back as lists."""
    if depth > MAX_DEPTH:
        raise DatabaseError("a document nested too deeply")
    if at + 5 > len(buf):
        raise DatabaseError("a document that ends partway")
    size = struct.unpack_from("<i", buf, at)[0]
    end = at + size
    if size < 5 or end > len(buf) or buf[end - 1] != 0:
        raise DatabaseError("a document of the wrong length")
    out, i = {}, at + 4
    while i < end - 1:
        tag = buf[i]
        name, i = _cstring(buf, i + 1)
        if i > end:
            raise DatabaseError("a document that ends partway")
        if tag == 0x01:
            value = struct.unpack_from("<d", buf, i)[0]
            i += 8
        elif tag == 0x02:
            n = struct.unpack_from("<i", buf, i)[0]
            if n < 1 or i + 4 + n > end or buf[i + 3 + n] != 0:
                raise DatabaseError("text of the wrong length")
            value = buf[i + 4:i + 3 + n].decode("utf-8", "replace")
            i += 4 + n
        elif tag in (0x03, 0x04):
            value, i = read_bson(buf, i, depth + 1)
            if tag == 0x04:
                value = list(value.values())
        elif tag == 0x05:
            n, sub = struct.unpack_from("<iB", buf, i)
            if n < 0 or i + 5 + n > end:
                raise DatabaseError("data of the wrong length")
            value = buf[i + 5:i + 5 + n]
            if sub == 4:
                value = value.hex()
            i += 5 + n
        elif tag == 0x07:
            value = buf[i:i + 12].hex()
            i += 12
        elif tag == 0x08:
            value = buf[i] != 0
            i += 1
        elif tag == 0x09:
            value = struct.unpack_from("<q", buf, i)[0]   # milliseconds since 1970, UTC
            i += 8
        elif tag in (0x0A, 0xFF, 0x7F):
            value = None
        elif tag == 0x10:
            value = struct.unpack_from("<i", buf, i)[0]
            i += 4
        elif tag == 0x12:
            value = struct.unpack_from("<q", buf, i)[0]
            i += 8
        elif tag == 0x13:
            value = None   # (a decimal: nothing Hoard reads is one)
            i += 16
        else:
            raise DatabaseError(f"a value of an unknown kind ({tag})")
        if i > end:
            raise DatabaseError("a value past its document's end")
        out[name] = value
    return out, end


def read(path: Path, names: tuple[str, ...]) -> dict[str, list[dict]]:
    """The documents in each of the named collections (names as LiteDB compares them: ignoring case). A collection
    the file doesn't have comes back empty; a missing file raises FileNotFoundError."""
    with open(path, "rb") as f:
        data = f.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise DatabaseError("larger than any Creator Companion database")
    pages = _Pages(data[:len(data) - len(data) % PAGE])
    if pages.count == 0:
        return {n: [] for n in names}
    if data[32:32 + len(HEADER_INFO)] != HEADER_INFO or data[59] != FILE_VERSION:
        raise DatabaseError("not a LiteDB 5 database")
    collections = {}
    if struct.unpack_from("<I", data, 192)[0]:
        collections, _ = read_bson(data[192:192 + 8000])
    by_name = {k.lower(): v for k, v in collections.items()}
    return {n: _documents(pages, by_name[n.lower()]) if isinstance(by_name.get(n.lower()), int) else []
            for n in names}


def _documents(pages: _Pages, page_id: int) -> list[dict]:
    at = pages.page(page_id, COLLECTION)
    buf = pages.data[at:at + PAGE]
    i, head, tail = 97, None, None
    for _ in range(buf[96]):   # each index: slot, type, name, expression, unique, head, tail, reserved, free list
        name, i = _cstring(buf, i + 2)
        _expression, i = _cstring(buf, i)
        head, tail = _address(buf, i + 1), _address(buf, i + 6)
        i += 1 + 5 + 5 + 1 + 4
        if name == "_id":
            break
    else:
        raise DatabaseError("a collection with no _id index")
    docs, seen, current = [], set(), head
    while current is not None:
        if current in seen or len(seen) > MAX_DOCUMENTS + 2:
            raise DatabaseError("an index that goes round in a loop")
        seen.add(current)
        node = pages.block(*current, INDEX)
        if len(node) < 22:
            raise DatabaseError("an index entry of the wrong length")
        if current not in (head, tail):
            data_at = _address(node, 2)
            if data_at is not None:
                docs.append(_document(pages, data_at))
        if current == tail:
            break
        current = _address(node, 17)   # the next entry at the lowest level
    return docs


def _document(pages: _Pages, at: tuple[int, int]) -> dict:
    parts, seen, current = [], set(), at
    while current is not None:
        if current in seen:
            raise DatabaseError("a document whose blocks go round in a loop")
        seen.add(current)
        block = pages.block(*current, DATA)
        parts.append(block[6:])
        if sum(map(len, parts)) > MAX_DOCUMENT:
            raise DatabaseError("a document larger than any real one")
        current = _address(block, 1)
    doc, _ = read_bson(b"".join(parts))
    return doc
