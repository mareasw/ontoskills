"""Document-first knowledge base: extract, segment, compile, verify, ask.

The pipeline is the one accepted in ADR 0002. The benchmark under
``benchmark/docbench`` keeps frozen copies so its measurements stay
reproducible; this package is the product implementation, and the segmenter is
parity-tested against the bench on the same text.
"""

from compiler.documents.model import Document, load_corpus, sha256_file
from compiler.documents.segment import chunk, segment

__all__ = ["Document", "load_corpus", "sha256_file", "chunk", "segment"]
