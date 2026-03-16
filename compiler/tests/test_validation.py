"""Tests for SHACL validation module."""

from rdflib import Graph


def test_validation_result_namedtuple():
    """Test that ValidationResult is a NamedTuple with correct fields."""
    from compiler.validator import ValidationResult

    # Create a result
    result = ValidationResult(
        conforms=True,
        results_text="All good",
        results_graph=None
    )
    assert result.conforms is True
    assert result.results_text == "All good"
    assert result.results_graph is None


def test_load_shacl_shapes():
    """Test that SHACL shapes file loads correctly."""
    from compiler.validator import load_shacl_shapes

    shapes = load_shacl_shapes()
    assert shapes is not None
    # Should contain our shapes (more than 0 triples)
    assert len(shapes) > 0
