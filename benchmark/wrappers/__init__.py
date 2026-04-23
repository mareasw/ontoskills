"""Benchmark wrappers: dataset loaders and runners for external benchmarks."""

from .gaia import GAIAWrapper
from .swebench import SWEBenchWrapper

__all__ = ["GAIAWrapper", "SWEBenchWrapper"]
