"""Align Literaturus blockquotes to Ionich; candidate labels, not reviewed gold."""

import hashlib
import json
import re
import unicodedata
from html.parser import HTMLParser

from eda import CACHE, OUT, download, paragraphs

URL = (
    "https://www.literaturus.ru/2016/12/"
    "dmitrij-ionych-starcev-obraz-harakteristika-jetapy-zhizni.html"
)


class Quotes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.items = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag == "blockquote":
            self.active = True
            self.current = []

    def handle_endtag(self, tag):
        if tag == "blockquote":
            self.active = False
            self.items.append("".join(self.current).strip())

    def handle_data(self, data):
        if self.active:
            self.current.append(data)


def normalize(text):
    # Keep a mapping from normalized character to original chapter offset.
    result, offsets = [], []
    for offset, char in enumerate(text):
        char = unicodedata.normalize("NFKC", char).lower().replace("ё", "е")
        for unit in char:
            if unit.isalnum():
                result.append(unit)
                offsets.append(offset)
    return "".join(result), offsets


def main():
    raw = download(URL, CACHE / "literaturus-starcev.html")
    parser = Quotes()
    parser.feed(raw.decode("utf-8"))
    if not parser.items:
        raise ValueError("No blockquotes: check source layout")
    chapters = []
    for chapter in range(1, 6):
        text = "\n\n".join(paragraphs((CACHE / f"ionych-{chapter:02}.html").read_bytes()))
        normalized, offsets = normalize(text)
        chapters.append((chapter, normalized, offsets))
    rows = []
    for index, quote in enumerate(parser.items, 1):
        # Ellipses denote omissions. Every nonempty segment must match in order.
        segments = [normalize(s)[0] for s in re.split(r"\.{3,}|…", quote.strip('"«» '))]
        segments = [s for s in segments if s]
        candidates = []
        if segments and all(len(s) >= 15 for s in segments):
            for chapter, text, offsets in chapters:
                for match in re.finditer(re.escape(segments[0]), text):
                    start, end = match.start(), match.end()
                    for segment in segments[1:]:
                        next_start = text.find(segment, end)
                        if next_start < 0:
                            break
                        end = next_start + len(segment)
                    else:
                        if end - start <= sum(map(len, segments)) + 500:
                            candidates.append(
                                {
                                    "chapter": chapter,
                                    "start": offsets[start],
                                    "end": offsets[end - 1] + 1,
                                }
                            )
        rows.append(
            {
                "quote_index": index,
                "quote_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                "status": "unique_candidate"
                if len(candidates) == 1
                else "unmatched"
                if not candidates
                else "ambiguous",
                "candidates": candidates,
            }
        )
    result = {
        "source": URL,
        "sha256_raw": hashlib.sha256(raw).hexdigest(),
        "offset_unit": "Unicode code points in cleaned chapter, end exclusive",
        "reviewed_gold": False,
        "quotes": rows,
    }
    (OUT / "quote_alignment.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        {
            status: sum(r["status"] == status for r in rows)
            for status in ["unique_candidate", "unmatched", "ambiguous"]
        }
    )


if __name__ == "__main__":
    main()
