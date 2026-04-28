#!/usr/bin/env python3
"""Tests for the deterministic extractors (INF, .NET metadata, MUI stub)."""

import json
import tempfile
from pathlib import Path

import jsonschema
import pytest

from extractors.inf import extract_inf
from extractors.dotnet_meta import extract_dotnet_metadata
from extractors.mui import extract_mui

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"

DOTNET_FIXTURE = FIXTURES / "System.DirectoryServices.dll"


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


def _validate_schema(data: dict, schema_name: str):
    schema = _load_schema(schema_name)
    jsonschema.validate(data, schema)


# ---------------------------------------------------------------------------
# INF tests
# ---------------------------------------------------------------------------

# Realistic Realtek-style INF content for testing
_SAMPLE_INF = """\
; Realtek PCIe GbE Family Controller
[Version]
Signature="$WINDOWS NT$"
Class=Net
ClassGuid={4d36e972-e325-11ce-bfc1-08002be10318}
Provider=%Realtek%
DriverVer=01/15/2020,10.38.115.2020
CatalogFile=netrtle.cat

[Manufacturer]
%Realtek%=Realtek,NTamd64

[Realtek.NTamd64]
%RTL8168.DeviceDesc%=RTL8168.NTamd64, PCI\\VEN_10EC&DEV_8168

[RTL8168.NTamd64.Services]
AddService=rt640x64, 2, RTL8168.Service

[RTL8168.Service]
ServiceType=1
StartType=3
ServiceBinary=%12%\\rt640x64.sys
AddReg=RTL8168.Params

[SourceDisksFiles]
rt640x64.sys=1
netrtle.cat=1

[Strings]
Realtek="Realtek Semiconductor Corp."
RTL8168.DeviceDesc="Realtek PCIe GbE Family Controller"
"""


class TestInfBasic:
    def test_extracts_all_fields(self):
        with tempfile.NamedTemporaryFile(suffix=".inf", mode="w", delete=False) as f:
            f.write(_SAMPLE_INF)
            f.flush()
            result = extract_inf(Path(f.name))

        # Version section
        assert result["version"]["Class"] == "Net"
        assert "4d36e972" in result["version"]["ClassGuid"]
        assert result["version"]["Provider"] == "%Realtek%"

        # Models
        assert len(result["models"]) >= 1
        model = result["models"][0]
        assert model["hardware_id"] == "PCI\\VEN_10EC&DEV_8168"
        assert model["install_section"] == "RTL8168.NTamd64"

        # DDInstall
        assert len(result["ddinstall"]) >= 1
        dd = result["ddinstall"][0]
        assert dd["service_binary"] == "rt640x64.sys"
        assert dd["start_type"] == 3

        # Source files
        assert "rt640x64.sys" in result["source_disks_files"]

        # Encoding
        assert result["encoding_uncertain"] is False

    def test_schema_valid(self):
        with tempfile.NamedTemporaryFile(suffix=".inf", mode="w", delete=False) as f:
            f.write(_SAMPLE_INF)
            f.flush()
            result = extract_inf(Path(f.name))
        _validate_schema(result, "inf.schema.json")


class TestInfEncoding:
    def test_utf16le_bom(self):
        """INF with UTF-16LE BOM is parsed correctly."""
        content = _SAMPLE_INF.encode("utf-16-le")
        # Prepend BOM
        bom_content = b"\xff\xfe" + content
        with tempfile.NamedTemporaryFile(suffix=".inf", delete=False) as f:
            f.write(bom_content)
            f.flush()
            result = extract_inf(Path(f.name))
        assert result["version"]["Class"] == "Net"
        assert result["encoding_uncertain"] is False


class TestInfMalformed:
    def test_duplicate_keys_handled(self):
        """INF with duplicate keys in a section doesn't crash."""
        content = """\
[Version]
Class=Net
Class=System
Provider=%Mfg%
DriverVer=01/01/2020,1.0.0.0

[Manufacturer]
%Mfg%=Models

[Models]
%Dev%=Install1, ACPI\\DEV0001
%Dev%=Install2, ACPI\\DEV0002
"""
        with tempfile.NamedTemporaryFile(suffix=".inf", mode="w", delete=False) as f:
            f.write(content)
            f.flush()
            result = extract_inf(Path(f.name))
        # Should parse without crashing; version has at least one Class entry
        assert "Class" in result["version"]
        assert result["encoding_uncertain"] is False


# ---------------------------------------------------------------------------
# .NET metadata tests
# ---------------------------------------------------------------------------

class TestDotNetAssemblyIdentity:
    def test_name_and_version(self):
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        ident = result["assembly_identity"]
        assert ident["name"] == "System.DirectoryServices"
        assert ident["version"] == "4.0.0.0"

    def test_public_key_token(self):
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        token = result["assembly_identity"]["public_key_token"]
        # Strong-named assembly — token should be 16 hex chars
        assert token is not None
        assert len(token) == 16
        # Known token for Microsoft public key
        assert token == "b03f5f7f11d50a3a"

    def test_target_framework_null(self):
        """target_framework is null (deferred), not absent."""
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        assert "target_framework" in result["assembly_identity"]
        assert result["assembly_identity"]["target_framework"] is None


class TestDotNetAssemblyRefs:
    def test_count(self):
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        assert len(result["referenced_assemblies"]) == 5

    def test_netstandard_ref(self):
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        names = [r["name"] for r in result["referenced_assemblies"]]
        assert "netstandard" in names

    def test_versions(self):
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        ns_ref = next(r for r in result["referenced_assemblies"] if r["name"] == "netstandard")
        assert ns_ref["version"] == "2.0.0.0"


class TestDotNetPublicTypes:
    def test_count(self):
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        assert len(result["public_type_surface"]) == 141

    def test_namespace_populated(self):
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        # All types should be in System.DirectoryServices namespace
        namespaces = set(t["namespace"] for t in result["public_type_surface"])
        assert "System.DirectoryServices" in namespaces


class TestDotNetPinvoke:
    def test_empty_for_reference_assembly(self):
        """Reference assembly has no P/Invoke surface."""
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        assert result["pinvoke_surface"] == []


class TestDotNetEscapeSurface:
    def test_has_escape_surface_from_typeref(self):
        """has_escape_surface is True from TypeRef to InteropServices.COMException,
        even though no AssemblyRef directly names InteropServices."""
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        assert result["has_escape_surface"] is True
        # Verify no AssemblyRef has escape_surface=True (it comes from TypeRef)
        assert all(not r["escape_surface"] for r in result["referenced_assemblies"])


class TestDotNetResources:
    def test_resource_streams(self):
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        assert len(result["resource_streams"]) == 2
        assert any("SR.resources" in r for r in result["resource_streams"])


class TestDotNetSchema:
    def test_schema_valid(self):
        result = extract_dotnet_metadata(DOTNET_FIXTURE)
        _validate_schema(result, "dotnet.schema.json")


# ---------------------------------------------------------------------------
# MUI stub test
# ---------------------------------------------------------------------------

class TestMuiStub:
    def test_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="no real .mui fixture"):
            extract_mui(Path("/any/path.mui"))
