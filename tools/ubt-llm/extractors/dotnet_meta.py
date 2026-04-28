"""Deterministic extractor for .NET assembly metadata.

Uses dnfile (pure-Python PE/.NET parser) to extract assembly identity,
referenced assemblies, public type surface, P/Invoke bridge table,
and resource streams.  No LLM calls.

dnfile API quirks (discovered during development, 2026-04-28):
  - String heap items (Name, TypeName, TypeNamespace, Culture) are
    HeapItemString objects, not str.  Use str() to coerce.
  - Binary heap items (PublicKey) are HeapItemBinary with a .value
    attribute (bytes), not directly convertible via bytes().
  - TypeDef attribute for namespace is .TypeNamespace, NOT .Namespace.
    The latter raises AttributeError with a "Did you mean?" hint.
  - TypeDef visibility flags are accessed via row.Flags.tdPublic and
    row.Flags.tdNestedPublic (bool attributes on ClrTypeAttr), not
    via bitmasking .value.
  - AssemblyRef public key field is .PublicKey (not .PublicKeyOrToken).
    Despite the ECMA-335 spec naming it PublicKeyOrToken, dnfile
    exposes it as .PublicKey.
  - ImplMap/ModuleRef tables may be None (not just empty) when the
    table doesn't exist in the metadata.
"""

import hashlib
from pathlib import Path

import dnfile


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Namespace prefixes that indicate "escape surface" — points where
# managed code can break out of the CLR sandbox.
_ESCAPE_MARKERS = (
    "System.Runtime.InteropServices",
    "System.Reflection.Emit",
    "System.Diagnostics.Process",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_public_key_token(public_key_bytes: bytes) -> str | None:
    """Derive the 8-byte public key token from a full public key.

    Algorithm (ECMA-335 §II.6.3):
    1. SHA-1 hash the full public key bytes.
    2. Take the last 8 bytes of the hash.
    3. Reverse byte order.
    4. Encode as lowercase hex.

    This matches what appears in assembly references, GAC paths,
    and [InternalsVisibleTo] attributes.
    """
    if not public_key_bytes:
        return None
    sha1 = hashlib.sha1(public_key_bytes).digest()
    token_bytes = sha1[-8:][::-1]
    return token_bytes.hex()


def _is_escape_namespace(namespace: str) -> bool:
    """Check if a namespace indicates escape-surface capability."""
    return any(namespace.startswith(m) for m in _ESCAPE_MARKERS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_dotnet_metadata(path: Path) -> dict:
    """Extract structured metadata from a .NET assembly.

    Returns a dict matching schema/dotnet.schema.json.

    has_escape_surface is derived from TWO sources:
      1. AssemblyRef names — if any referenced assembly name starts
         with an escape-marker prefix.
      2. TypeRef namespaces — if any type reference's namespace starts
         with an escape-marker prefix.
    Both sources contribute to the top-level flag.  A True from either
    source sets it True.  The individual escape_surface flags on
    AssemblyRef entries only reflect source #1; source #2 can set the
    top-level flag even when all AssemblyRef flags are False.
    """
    pe = dnfile.dnPE(str(path))

    try:
        result = _extract_all(pe)
    finally:
        pe.close()

    return result


def _extract_all(pe: dnfile.dnPE) -> dict:
    """Internal extraction logic."""
    assembly_identity = _extract_assembly_identity(pe)
    referenced_assemblies = _extract_assembly_refs(pe)
    public_type_surface = _extract_public_types(pe)
    pinvoke_surface = _extract_pinvoke(pe)
    resource_streams = _extract_resources(pe)

    # Escape-surface detection from two sources:
    # Source 1: AssemblyRef names (already flagged per-ref)
    has_escape_from_refs = any(r["escape_surface"] for r in referenced_assemblies)
    # Source 2: TypeRef namespaces
    has_escape_from_typerefs = _check_typeref_escape(pe)

    return {
        "assembly_identity": assembly_identity,
        "referenced_assemblies": referenced_assemblies,
        "public_type_surface": public_type_surface,
        "pinvoke_surface": pinvoke_surface,
        "resource_streams": resource_streams,
        "has_escape_surface": has_escape_from_refs or has_escape_from_typerefs,
    }


def _extract_assembly_identity(pe: dnfile.dnPE) -> dict:
    """Extract identity from the Assembly metadata table."""
    if not pe.net or not pe.net.mdtables or not pe.net.mdtables.Assembly:
        return {
            "name": None, "version": None, "culture": None,
            "public_key_token": None, "target_framework": None,
        }

    row = pe.net.mdtables.Assembly[0]

    # str() coerces HeapItemString to Python str
    name = str(row.Name)
    version = f"{row.MajorVersion}.{row.MinorVersion}.{row.BuildNumber}.{row.RevisionNumber}"

    # Culture: HeapItemString, empty string means neutral culture
    culture_str = str(row.Culture) if row.Culture else None
    culture = culture_str if culture_str else None

    # PublicKey: HeapItemBinary with .value attribute (bytes)
    pk = row.PublicKey
    pk_bytes = pk.value if hasattr(pk, "value") and pk.value else None
    token = _compute_public_key_token(pk_bytes)

    return {
        "name": name,
        "version": version,
        "culture": culture,
        "public_key_token": token,
        # target_framework: requires parsing CustomAttribute constructor
        # blob arguments to find TargetFrameworkAttribute.  Deferred.
        # null means "not extracted", not "absent."
        "target_framework": None,
    }


def _extract_assembly_refs(pe: dnfile.dnPE) -> list[dict]:
    """Extract referenced assemblies from AssemblyRef table."""
    refs = []
    if not pe.net or not pe.net.mdtables or not pe.net.mdtables.AssemblyRef:
        return refs

    for row in pe.net.mdtables.AssemblyRef:
        name = str(row.Name)
        version = f"{row.MajorVersion}.{row.MinorVersion}.{row.BuildNumber}.{row.RevisionNumber}"

        # dnfile exposes the token/key as .PublicKey (not .PublicKeyOrToken
        # as ECMA-335 names it).  For AssemblyRef rows this is typically
        # the 8-byte token, not the full key.
        pk = row.PublicKey
        pk_hex = pk.value.hex() if hasattr(pk, "value") and pk.value else None

        refs.append({
            "name": name,
            "version": version,
            "public_key_token": pk_hex,
            "escape_surface": _is_escape_namespace(name),
        })

    return refs


def _extract_public_types(pe: dnfile.dnPE) -> list[dict]:
    """Extract public type definitions with method counts.

    Uses TypeDef.Flags.tdPublic and .tdNestedPublic to filter visibility.
    Method counts are derived from MethodList index ranges between
    consecutive TypeDef rows.
    """
    types = []
    if not pe.net or not pe.net.mdtables or not pe.net.mdtables.TypeDef:
        return types

    typedef_table = pe.net.mdtables.TypeDef
    total_methods = pe.net.mdtables.MethodDef.num_rows if pe.net.mdtables.MethodDef else 0

    for i, row in enumerate(typedef_table):
        # Visibility check via ClrTypeAttr bool flags
        if not (row.Flags.tdPublic or row.Flags.tdNestedPublic):
            continue

        # TypeNamespace (not Namespace — dnfile raises AttributeError
        # with "Did you mean: 'TypeNamespace'?" if you use .Namespace)
        ns = str(row.TypeNamespace) if row.TypeNamespace else ""
        name = str(row.TypeName)
        kind = "interface" if row.Flags.tdInterface else "class"

        # Method count: difference between this row's MethodList and
        # the next row's MethodList (or total methods for the last row)
        method_start = row.MethodList.row_index if hasattr(row.MethodList, "row_index") else 0
        if i + 1 < typedef_table.num_rows:
            next_row = typedef_table[i + 1]
            method_end = next_row.MethodList.row_index if hasattr(next_row.MethodList, "row_index") else method_start
        else:
            method_end = total_methods + 1  # 1-based indexing
        method_count = max(0, method_end - method_start)

        types.append({
            "namespace": ns,
            "name": name,
            "kind": kind,
            "method_count": method_count,
        })

    return types


def _extract_pinvoke(pe: dnfile.dnPE) -> list[dict]:
    """Extract P/Invoke declarations from ImplMap + ModuleRef tables.

    ImplMap rows link a managed MethodDef to a native entry point in
    a DLL named in the ModuleRef table.  This is the bridge table from
    .NET back to native code.
    """
    entries = []
    if not pe.net or not pe.net.mdtables:
        return entries

    # ImplMap and ModuleRef may be None (not just empty) when the
    # metadata table doesn't exist in the assembly.
    impl_map = pe.net.mdtables.ImplMap
    if impl_map is None:
        return entries

    module_ref = pe.net.mdtables.ModuleRef

    for row in impl_map:
        import_name = str(row.ImportName) if row.ImportName else None

        # ImportScope references a ModuleRef row
        scope = row.ImportScope
        native_dll = None
        if scope and module_ref:
            # scope is a coded index; resolve to ModuleRef row
            if hasattr(scope, "row") and scope.row:
                native_dll = str(scope.row.Name) if hasattr(scope.row, "Name") else None
            elif hasattr(scope, "Name"):
                native_dll = str(scope.Name)

        # MemberForwarded references the managed method
        member = row.MemberForwarded
        managed_method = None
        if member:
            if hasattr(member, "row") and member.row and hasattr(member.row, "Name"):
                managed_method = str(member.row.Name)
            elif hasattr(member, "Name"):
                managed_method = str(member.Name)

        entries.append({
            "managed_method": managed_method,
            "native_dll": native_dll,
            "entry_point": import_name,
        })

    return entries


def _extract_resources(pe: dnfile.dnPE) -> list[str]:
    """Extract manifest resource stream names."""
    resources = []
    if not pe.net or not pe.net.mdtables or not pe.net.mdtables.ManifestResource:
        return resources

    for row in pe.net.mdtables.ManifestResource:
        name = str(row.Name) if row.Name else None
        if name:
            resources.append(name)

    return resources


def _check_typeref_escape(pe: dnfile.dnPE) -> bool:
    """Check TypeRef table for escape-surface namespace references.

    This catches cases like System.DirectoryServices.dll which has a
    TypeRef to System.Runtime.InteropServices.COMException even though
    its AssemblyRefs don't directly name System.Runtime.InteropServices.
    """
    if not pe.net or not pe.net.mdtables or not pe.net.mdtables.TypeRef:
        return False

    for row in pe.net.mdtables.TypeRef:
        # TypeNamespace, same pattern as TypeDef
        ns = str(row.TypeNamespace) if row.TypeNamespace else ""
        if _is_escape_namespace(ns):
            return True

    return False
