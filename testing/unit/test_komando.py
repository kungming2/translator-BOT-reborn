"""
testing/unit/test_komando.py
Tests for Komando class
"""

import pytest

from models.komando import Komando  # Replace with actual import path


class TestKomando:
    """Test suite for Komando class functionality"""

    def test_initialization_with_name_only(self):
        """Test Komando initialization with only name"""
        # When
        komando = Komando("identify")

        # Then
        assert komando.name == "identify"
        assert komando.data is None

    def test_initialization_with_name_and_data(self):
        """Test Komando initialization with name and data"""
        # When
        komando = Komando("translated", ["es"])

        # Then
        assert komando.name == "translated"
        assert komando.data == ["es"]

    def test_initialization_with_complex_data(self):
        """Test Komando initialization with complex data structures"""
        test_cases = [
            (["la", "grc"]),  # Multiple languages
            (["string1", "string2", "string3"]),  # Multiple strings
            ([]),  # Empty list
            (["single_string"]),  # Single string in list
        ]

        for data in test_cases:
            # When
            komando = Komando("lookup", data)

            # Then
            assert komando.name == "lookup"
            assert komando.data == data

    def test_repr_without_data(self):
        """Test __repr__ method when data is None"""
        # Given
        komando = Komando("identify")

        # When
        result = repr(komando)

        # Then
        expected = "Komando(name='identify', data=None)"
        assert result == expected

    def test_repr_with_data(self):
        """Test __repr__ method when data is provided"""
        # Given
        komando = Komando("translated", ["es"])

        # When
        result = repr(komando)

        # Then
        expected = "Komando(name='translated', data=['es'])"
        assert result == expected

    def test_repr_with_complex_data(self):
        """Test __repr__ method with complex data"""
        # Given
        komando = Komando("wiki", ["string1", "string2"])

        # When
        result = repr(komando)

        # Then
        expected = "Komando(name='wiki', data=['string1', 'string2'])"
        assert result == expected

    def test_to_dict_without_data(self):
        """Test to_dict method when data is None"""
        # Given
        komando = Komando("identify")

        # When
        result = komando.to_dict()

        # Then
        expected = {"name": "identify", "data": None}
        assert result == expected

    def test_to_dict_with_data(self):
        """Test to_dict method when data is provided"""
        # Given
        komando = Komando("translated", ["la", "grc"])

        # When
        result = komando.to_dict()

        # Then
        expected = {"name": "translated", "data": ["la", "grc"]}
        assert result == expected

    def test_to_dict_preserves_data_structure(self):
        """Test that to_dict preserves the exact data structure"""
        test_cases = [
            [],
            ["es"],
            ["la", "grc"],
            ["string1", "string2", "string3"],
        ]

        for data in test_cases:
            # Given
            komando = Komando("test", data)

            # When
            result = komando.to_dict()

            # Then
            assert result["name"] == "test"
            assert result["data"] == data
            assert isinstance(result["data"], type(data))

    @pytest.mark.parametrize(
        "name,data",
        [
            ("identify", None),
            ("translated", ["es"]),
            ("lookup", ["search_term"]),
            ("wiki", ["topic1", "topic2"]),
            ("command", []),
        ],
    )
    def test_round_trip_dict_conversion(self, name, data):
        """Test that to_dict preserves all data for potential reconstruction"""
        # Given
        original = Komando(name, data)

        # When
        dict_repr = original.to_dict()

        # Then - the dictionary should contain all necessary data
        assert dict_repr["name"] == name
        assert dict_repr["data"] == data

    def test_different_name_types(self):
        """Test Komando with different types of names"""
        test_cases = [
            "identify",
            "translated",
            "lookup",
            "wiki",
            "custom_command",
            "another_command",
        ]

        for name in test_cases:
            # When
            komando = Komando(name)

            # Then
            assert komando.name == name
            assert komando.to_dict()["name"] == name


class TestKomandoEdgeCases:
    """Test edge cases and potential error conditions"""

    def test_empty_string_name(self):
        """Test Komando with empty string name"""
        # When
        komando = Komando("")

        # Then
        assert komando.name == ""
        assert komando.to_dict()["name"] == ""

    def test_none_data_explicit(self):
        """Test Komando with explicit None data"""
        # When
        komando = Komando("test", None)

        # Then
        assert komando.name == "test"
        assert komando.data is None
        assert komando.to_dict()["data"] is None

    def test_various_data_types(self):
        """Test Komando with various data types (though list/None are expected)"""
        # Note: This tests behavior with unexpected data types
        komando = Komando("test", "unexpected_string")
        assert komando.data == "unexpected_string"

        komando = Komando("test", 123)
        assert komando.data == 123

        komando = Komando("test", {"key": "value"})
        assert komando.data == {"key": "value"}


class TestKomandoIntegration:
    """Integration-style tests for Komando class"""

    def test_komando_in_data_structures(self):
        """Test Komando objects work well in common data structures"""
        # Given
        commands = [
            Komando("identify"),
            Komando("translated", ["es"]),
            Komando("lookup", ["search_term"]),
        ]

        # When
        command_dict = {cmd.name: cmd for cmd in commands}
        command_reprs = [repr(cmd) for cmd in commands]
        command_dicts = [cmd.to_dict() for cmd in commands]

        # Then
        assert len(command_dict) == 3
        assert all(isinstance(repr_str, str) for repr_str in command_reprs)
        assert all(isinstance(cmd_dict, dict) for cmd_dict in command_dicts)

    def test_serialization_ready(self):
        """Test that to_dict produces JSON-serializable output"""
        import json

        test_cases = [
            Komando("identify"),
            Komando("translated", ["es"]),
            Komando("lookup", ["term1", "term2"]),
        ]

        for komando in test_cases:
            # When
            data = komando.to_dict()

            # Then - should be JSON serializable
            json_str = json.dumps(data)
            reconstructed = json.loads(json_str)

            assert reconstructed["name"] == komando.name
            assert reconstructed["data"] == komando.data
