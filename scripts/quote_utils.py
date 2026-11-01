"""Quote-block parsing and character-preserving search normalization."""

import unicodedata
from html.parser import HTMLParser


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
