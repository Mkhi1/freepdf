"""Offline translation with the Argos Translate models, run directly through CTranslate2.

argostranslate is only needed to download models. Running them here skips its sentence splitter,
which would load PyTorch, stanza and spaCy (hundreds of MB of RAM) for no gain."""
import json
import os
import re
import unicodedata
from pathlib import Path

from ..core import ToolError, resource_dir

BEAM_SIZE = 4
LENGTH_PENALTY = 0.2
CPU_THREADS = 2
SENTENCE_END = re.compile(r"(?<=[.!?؟۔…])[\"')\]”»]*\s+|\n+")
ABBREVIATION = re.compile(
    r"(?:\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|Fig|No|Inc|Ltd|Co|approx|Vol|pp)|\b[A-Z]|\be\.g|\bi\.e"
    r"|(?<![ء-ي])[ء-ي])\.$")
_loaded: dict[tuple[str, str], "Model"] = {}


def configure_environment() -> Path:
    """Keep every Argos file under the app's resource folder, never in the user profile."""
    base = resource_dir("argos")
    for name, sub in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache")):
        os.environ[name] = str(base / sub)
    os.environ["ARGOS_PACKAGES_DIR"] = str(base / "packages")
    return base


def split_sentences(text: str) -> list[str]:
    """Sentences for English and Arabic: . ! ? and the Arabic question mark, keeping abbreviations whole."""
    text = unicodedata.normalize("NFKC", text)  # PDF Arabic comes out as joined presentation forms
    pieces = [p.strip() for p in SENTENCE_END.split(text) if p and p.strip()]
    merged: list[str] = []
    for piece in pieces:
        if merged and ABBREVIATION.search(merged[-1]):
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)
    return merged


class Model:
    """One installed language pair: SentencePiece tokenizer plus a CTranslate2 network."""

    def __init__(self, folder: Path):
        import ctranslate2
        import sentencepiece

        meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        self.prefix = meta.get("target_prefix", "")
        self.tokens = sentencepiece.SentencePieceProcessor(model_file=str(folder / "sentencepiece.model"))
        self.net = ctranslate2.Translator(str(folder / "model"), device="cpu", inter_threads=1,
                                          intra_threads=CPU_THREADS, compute_type="int8")

    def translate(self, sentences: list[str]) -> list[str]:
        if not sentences:
            return []
        pieces = [self.tokens.encode(s, out_type=str) for s in sentences]
        prefix = [[self.prefix]] * len(pieces) if self.prefix else None
        out = self.net.translate_batch(pieces, target_prefix=prefix, replace_unknowns=True,
                                       max_batch_size=1024, batch_type="tokens", beam_size=BEAM_SIZE,
                                       length_penalty=LENGTH_PENALTY)
        return [self._clean(self.tokens.decode_pieces(r.hypotheses[0])) for r in out]

    def _clean(self, text: str) -> str:
        text = text.replace("▁", " ").strip()
        return text[len(self.prefix):].strip() if self.prefix and text.startswith(self.prefix) else text


def _package_folder(source: str, target: str) -> Path:
    return resource_dir("argos") / "packages" / f"{source}_{target}"


def _load(source: str, target: str) -> Model:
    key = (source, target)
    if key not in _loaded:
        folder = _package_folder(source, target)
        if not (folder / "model" / "model.bin").is_file():
            raise ToolError("missing_resource",
                            f"The {source} to {target} translation model is not installed. "
                            "Reinstall Free PDF or add the language pack.")
        _loaded[key] = Model(folder)
    return _loaded[key]


def route(source: str, target: str) -> list[tuple[str, str]]:
    """Direct pair when installed, otherwise through English."""
    if _package_folder(source, target).is_dir():
        return [(source, target)]
    if "en" not in (source, target) and _package_folder(source, "en").is_dir() \
            and _package_folder("en", target).is_dir():
        return [(source, "en"), ("en", target)]
    raise ToolError("missing_resource", f"Translating {source} to {target} is not available offline yet.")


def translate_sentences(sentences: list[str], source: str, target: str) -> list[str]:
    """Translate in one batch per hop. Models load here, the first time a translation is requested."""
    if source == target:
        return list(sentences)
    current = list(sentences)
    for hop_source, hop_target in route(source, target):
        current = _load(hop_source, hop_target).translate(current)
    return current


def release_models() -> None:
    _loaded.clear()


def translate_text(text: str, source: str, target: str) -> str:
    """Translate a block of text sentence by sentence, keeping paragraph breaks."""
    paragraphs = [p for p in text.split("\n")]
    flat: list[tuple[int, str]] = [(i, s) for i, p in enumerate(paragraphs) for s in split_sentences(p)]
    done = translate_sentences([s for _, s in flat], source, target)
    grouped: dict[int, list[str]] = {}
    for (index, _), value in zip(flat, done):
        grouped.setdefault(index, []).append(value)
    return "\n".join(" ".join(grouped.get(i, [])) for i in range(len(paragraphs)))
