"""Tests for Layer 2 convention discovery modules."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from capl_forge.conventions.prefix_discovery import (
    discover_prefixes,
    discover_suffixes,
    strip_affixes,
)
from capl_forge.conventions.file_role_discovery import classify_dbc_bus_role
from capl_forge.conventions.stimulus_dominance import classify_stimulus_dominance


class TestPrefixDiscovery:
    def test_discovers_common_prefix(self):
        """Should discover prefixes that appear frequently."""
        names = ["env_Speed", "env_Temperature", "env_Pressure", "vehicle_RPM"]
        prefixes = discover_prefixes(names, min_frequency=0.3)
        assert "env_" in prefixes

    def test_empty_input(self):
        discover_prefixes([]) == []

    def test_no_common_prefix(self):
        names = ["Speed", "Temperature", "Pressure"]
        prefixes = discover_prefixes(names)
        assert len(prefixes) == 0

    def test_strip_affixes_with_discovered(self):
        prefixes = ["env_", "sim_"]
        suffixes = ["_req", "_D"]
        result, original = strip_affixes("env_Speed_req", prefixes, suffixes)
        assert result == "speed"
        assert original == "env_Speed_req"

    def test_strip_affixes_no_match(self):
        result, original = strip_affixes("Speed", [], [])
        assert result == "speed"

    def test_suffix_discovery(self):
        names = ["Speed_req", "Temp_req", "Pressure_D"]
        suffixes = discover_suffixes(names, min_frequency=0.3)
        assert "_req" in suffixes


class TestFileRoleDiscovery:
    def test_env_dbc_by_content(self, tmp_path):
        """Should classify DBC with EV_ defs as 'env'."""
        env_dbc = tmp_path / "env.dbc"
        env_dbc.write_text("EV_ TEST : 0 [0|1] \"\" 0 1 readwrite\nBA_ \"GenEnvVarClassName\" EV_ TEST \"Test\"")
        role = classify_dbc_bus_role(env_dbc)
        assert role == "env"

    def test_vehicle_dbc_default(self, tmp_path):
        """Should default to 'vehicle' for generic DBC."""
        vehicle_dbc = tmp_path / "vehicle.dbc"
        vehicle_dbc.write_text("VERSION ''\nNS_ :")
        role = classify_dbc_bus_role(vehicle_dbc)
        assert role == "vehicle"

    def test_known_roles_override(self, tmp_path):
        """Known roles from conventions should override content analysis."""
        env_dbc = tmp_path / "some_env_file.dbc"
        env_dbc.write_text("BO_ 100 TestMsg: 8 Vector__XXX")
        known_roles = {"env": ["env", "environment"]}
        role = classify_dbc_bus_role(env_dbc, known_roles=known_roles)
        assert role == "env"


class TestStimulusDominance:
    def test_envvar_dominant(self):
        assert classify_stimulus_dominance(10, 2, 1) == "envvar"

    def test_sysvar_dominant(self):
        assert classify_stimulus_dominance(1, 10, 2) == "sysvar"

    def test_direct_dominant(self):
        assert classify_stimulus_dominance(1, 2, 10) == "direct"

    def test_mixed(self):
        assert classify_stimulus_dominance(5, 4, 3) == "mixed"

    def test_zero_total(self):
        assert classify_stimulus_dominance(0, 0, 0) == "unknown"
