"""Deterministic extractor for Windows INF (driver installation) files.

Parses [Version], [Manufacturer], model sections, [DDInstall.Services],
and [SourceDisksFiles] to produce a structured representation of the
driver installation metadata.  No LLM calls.

Encoding detection order: UTF-16LE BOM → UTF-8 → Windows-1252 → latin-1.
"""

import configparser
import io
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Encoding detection
# ---------------------------------------------------------------------------

def _read_inf_text(path: Path) -> tuple[str, bool]:
    """Read INF file as text, trying multiple encodings.

    Returns (text, encoding_uncertain).  encoding_uncertain is True only
    if we fell all the way back to latin-1.
    """
    raw = path.read_bytes()

    # UTF-16LE with BOM
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le"), False

    # UTF-8 (with or without BOM)
    try:
        text = raw.decode("utf-8")
        return text.lstrip("\ufeff"), False
    except UnicodeDecodeError:
        pass

    # Windows-1252 (superset of latin-1, common in older Microsoft files)
    try:
        return raw.decode("cp1252"), False
    except UnicodeDecodeError:
        pass

    # latin-1 never raises — flag as uncertain
    return raw.decode("latin-1"), True


# ---------------------------------------------------------------------------
# Section parsing helpers
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^\[([^\]]+)\]\s*$", re.MULTILINE)


def _manual_parse_sections(text: str) -> dict[str, list[str]]:
    """Parse INF into sections manually when configparser fails.

    Returns {section_name_lower: [lines...]}.  Handles duplicate keys
    and Microsoft INF quirks that configparser rejects.
    """
    sections: dict[str, list[str]] = {}
    current_section = None
    for line in text.splitlines():
        line = line.strip()
        # Skip comments and blank lines
        if not line or line.startswith(";"):
            continue
        m = _SECTION_RE.match(line)
        if m:
            current_section = m.group(1).strip().lower()
            sections.setdefault(current_section, [])
        elif current_section is not None:
            sections[current_section].append(line)
    return sections


def _try_configparser(text: str) -> configparser.ConfigParser | None:
    """Try parsing with configparser (strict=False).

    Returns the parser on success, None on failure.
    """
    cp = configparser.ConfigParser(
        strict=False,
        interpolation=None,
        comment_prefixes=(";",),
        inline_comment_prefixes=(";",),
        delimiters=("=",),
    )
    # configparser requires lowercase option names by default
    cp.optionxform = str
    try:
        cp.read_string(text)
        return cp
    except (configparser.Error, KeyError):
        return None


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def _extract_version(sections: dict[str, list[str]], cp: configparser.ConfigParser | None) -> dict:
    """Extract [Version] section fields."""
    result = {}
    if cp and cp.has_section("Version"):
        for key in cp.options("Version"):
            result[key] = cp.get("Version", key).strip().strip('"')
    elif "version" in sections:
        for line in sections["version"]:
            if "=" in line:
                key, _, val = line.partition("=")
                result[key.strip()] = val.strip().strip('"')
    return result


def _extract_models(sections: dict[str, list[str]], cp: configparser.ConfigParser | None) -> list[dict]:
    """Extract hardware models from [Manufacturer] → model sections."""
    models = []

    # Get manufacturer entries: each line is Mfg = models-section[,decoration]
    mfg_lines = []
    if cp and cp.has_section("Manufacturer"):
        for key in cp.options("Manufacturer"):
            mfg_lines.append(cp.get("Manufacturer", key))
    elif "manufacturer" in sections:
        for line in sections["manufacturer"]:
            if "=" in line:
                _, _, val = line.partition("=")
                mfg_lines.append(val.strip())

    # Each mfg line points to one or more model sections
    for mfg_val in mfg_lines:
        # Format: %MfgName% = models-section[,NTamd64][,NTamd64.10.0]
        parts = [p.strip() for p in mfg_val.split(",")]
        # The model section names to look for (with and without decorations)
        section_candidates = []
        if parts:
            base = parts[0].strip().strip("%")
            section_candidates.append(base.lower())
            for decoration in parts[1:]:
                section_candidates.append(f"{base}.{decoration}".lower())

        for sec_name in section_candidates:
            sec_lines = []
            if cp and cp.has_section(sec_name):
                # configparser lowercases section names — try original case too
                for key in cp.options(sec_name):
                    sec_lines.append((key, cp.get(sec_name, key)))
            # Also check manual sections (case-insensitive)
            if not sec_lines and sec_name in sections:
                for line in sections[sec_name]:
                    if "=" in line:
                        key, _, val = line.partition("=")
                        sec_lines.append((key.strip(), val.strip()))

            for desc, install_info in sec_lines:
                # Format: description = install-section, hardware-id[, compat-id...]
                parts2 = [p.strip() for p in install_info.split(",")]
                if len(parts2) >= 2:
                    models.append({
                        "hardware_id": parts2[1],
                        "install_section": parts2[0],
                        "description": desc.strip().strip("%"),
                    })

    return models


def _extract_ddinstall(sections: dict[str, list[str]], cp: configparser.ConfigParser | None, models: list[dict]) -> list[dict]:
    """Extract DDInstall service information for each model's install section."""
    results = []

    for model in models:
        install_sec = model["install_section"].lower()
        svc_sec = f"{install_sec}.services"

        # Find ServiceInstall directive
        svc_lines = []
        if cp and cp.has_section(svc_sec):
            for key in cp.options(svc_sec):
                svc_lines.append((key, cp.get(svc_sec, key)))
        elif svc_sec in sections:
            for line in sections[svc_sec]:
                if "=" in line:
                    key, _, val = line.partition("=")
                    svc_lines.append((key.strip(), val.strip()))

        for directive, val in svc_lines:
            if directive.lower() != "addservice":
                continue
            # AddService = ServiceName, flags, service-install-section
            parts = [p.strip() for p in val.split(",")]
            if len(parts) < 3:
                continue
            svc_install_sec = parts[2].lower()

            # Read the service-install section
            binary = None
            start_type = None
            reg_adds = []

            si_lines = []
            if cp and cp.has_section(svc_install_sec):
                for key in cp.options(svc_install_sec):
                    si_lines.append((key, cp.get(svc_install_sec, key)))
            elif svc_install_sec in sections:
                for line in sections[svc_install_sec]:
                    if "=" in line:
                        key2, _, val2 = line.partition("=")
                        si_lines.append((key2.strip(), val2.strip()))

            for key, val in si_lines:
                kl = key.lower()
                if kl == "servicebinary":
                    # Format: %12%\filename.sys or similar
                    binary = val.strip().split("\\")[-1]
                elif kl == "starttype":
                    try:
                        start_type = int(val.strip())
                    except ValueError:
                        start_type = None
                elif kl == "addreg":
                    reg_adds.append(val.strip())

            results.append({
                "section": model["install_section"],
                "service_binary": binary,
                "start_type": start_type,
                "registry_adds": reg_adds,
            })

    return results


def _extract_source_disks_files(sections: dict[str, list[str]], cp: configparser.ConfigParser | None) -> list[str]:
    """Extract filenames from [SourceDisksFiles]."""
    files = []

    # Try multiple section name variants (some INFs use decorated names)
    for sec_name in ("sourcedisksfiles", "sourcedisksfiles.amd64", "sourcedisksfiles.x86"):
        if cp and cp.has_section(sec_name):
            files.extend(cp.options(sec_name))
        elif sec_name in sections:
            for line in sections[sec_name]:
                if "=" in line:
                    fname, _, _ = line.partition("=")
                    files.append(fname.strip())

    return files


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_inf(path: Path) -> dict:
    """Extract structured metadata from a Windows INF file.

    Returns a dict matching schema/inf.schema.json.
    """
    text, encoding_uncertain = _read_inf_text(path)

    # Try configparser first, fall back to manual
    cp = _try_configparser(text)
    sections = _manual_parse_sections(text)

    version = _extract_version(sections, cp)
    models = _extract_models(sections, cp)
    ddinstall = _extract_ddinstall(sections, cp, models)
    source_files = _extract_source_disks_files(sections, cp)

    return {
        "version": version,
        "models": models,
        "ddinstall": ddinstall,
        "source_disks_files": source_files,
        "encoding_uncertain": encoding_uncertain,
    }
