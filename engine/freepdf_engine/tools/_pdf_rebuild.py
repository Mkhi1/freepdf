"""Last-resort recovery for PDFs whose end is missing (cut-off downloads, interrupted saves)."""
import re

OBJECT_START = re.compile(rb"(?m)(?:^|\s)(\d+)\s+(\d+)\s+obj\b")
PAGE_TYPE = re.compile(rb"/Type\s*/Page(?![A-Za-z])")
PARENT_REF = re.compile(rb"/Parent\s+(\d+)\s+(\d+)\s+R")
HEAD_BYTES = 4000


def rebuild_tail(data: bytes) -> bytes | None:
    """Append a page tree, catalog and trailer built from the objects that survived.

    Returns None when no page object can be found.
    """
    if not data.lstrip().startswith(b"%PDF"):
        return None
    starts = list(OBJECT_START.finditer(data))
    pages, parent, highest = [], None, 0
    for match in starts:
        number = int(match.group(1))
        highest = max(highest, number)
        head = data[match.end(): match.end() + HEAD_BYTES].split(b"endobj")[0].split(b"stream")[0]
        if PAGE_TYPE.search(head):
            if number not in pages:
                pages.append(number)
            link = PARENT_REF.search(head)
            parent = parent or (int(link.group(1)) if link else None)
    if not pages:
        return None
    tree = parent if parent else highest + 1
    catalog = max(highest, tree) + 1
    kids = " ".join(f"{n} 0 R" for n in pages)
    tail = (
        f"\n{tree} 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>\nendobj\n"
        f"{catalog} 0 obj\n<< /Type /Catalog /Pages {tree} 0 R >>\nendobj\n"
        f"trailer\n<< /Size {catalog + 1} /Root {catalog} 0 R >>\nstartxref\n0\n%%EOF\n"
    )
    return data + tail.encode("ascii")
