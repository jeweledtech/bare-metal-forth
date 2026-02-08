# Bare-Metal Forth Module Manifest System

## Overview

The module manifest system provides an XML-based declaration format for Bare-Metal Forth loadable modules. Each manifest describes a module's metadata, dependencies, exported words, and embedded Forth logic. The XML format serves as a **build-time** artifact: a manifest processor reads the XML, resolves dependencies, and generates a Forth load script that the Bare-Metal Forth interpreter executes.

This bridges the gap between structured, tooling-friendly module descriptions and the runtime `USING` mechanism already implemented in `dict_system.fth`.

## Design Goals

1. **Machine-readable module metadata** - tools can enumerate, validate, and resolve dependencies before loading
2. **Human-readable documentation** - the manifest doubles as module documentation
3. **Maps to existing USING system** - manifests generate Forth code that uses `USING`, `DICT-REGISTER`, and standard Forth definitions
4. **No runtime XML parsing** - Bare-Metal Forth never sees XML; the processor outputs pure Forth

## Manifest Format

### Minimal Example

```xml
<?xml version="1.0" encoding="UTF-8"?>
<bmforth-manifest version="1.0">
  <module name="RTL8139" version="0.1.0">
    <description>RealTek RTL8139 network interface driver</description>
    <vendor>RealTek</vendor>
    <pci-id vendor="10EC" device="8139"/>

    <requires>
      <use module="HARDWARE" version=">=0.1.0"/>
    </requires>

    <definitions>
      <use file="hardware.fth"/>
      <use file="rtl8139.fth"/>
    </definitions>

    <exports>
      <word name="RTL-INIT"   stack="( base-port -- )" description="Initialize RTL8139"/>
      <word name="RTL-RESET"  stack="( -- )"           description="Reset the NIC"/>
      <word name="RTL-TX"     stack="( addr len -- )"   description="Transmit packet"/>
      <word name="RTL-RX"     stack="( -- addr len )"   description="Receive packet"/>
    </exports>
  </module>
</bmforth-manifest>
```

### Full Schema

```xml
<bmforth-manifest version="1.0">

  <module name="NAME" version="MAJOR.MINOR.PATCH">

    <!-- Human-readable description -->
    <description>Text description of the module</description>

    <!-- Optional hardware identification -->
    <vendor>Vendor name</vendor>
    <pci-id vendor="XXXX" device="YYYY"/>

    <!-- Module dependencies -->
    <requires>
      <!-- Each dependency specifies a module and optional version constraint -->
      <use module="MODULE_NAME" version=">=X.Y.Z"/>
      <use module="MODULE_NAME"/>  <!-- any version -->
    </requires>

    <!-- Forth source files to load (in order) -->
    <definitions>
      <use file="path/to/file.fth"/>
      <use file="path/to/another.fth"/>
    </definitions>

    <!-- Inline Forth code (loaded after <definitions> files) -->
    <logic><![CDATA[
      \ Forth code here
      : MODULE-WORD  ( -- )
          ." Hello from module" CR
      ;
    ]]></logic>

    <!-- Public API of this module -->
    <exports>
      <word name="WORD-NAME"
            stack="( inputs -- outputs )"
            description="What this word does"/>
    </exports>

    <!-- Module flags -->
    <flags>
      <flag name="system"/>     <!-- Cannot be unloaded -->
      <flag name="hardware"/>   <!-- Contains hardware access -->
      <flag name="immediate"/>  <!-- Load at boot -->
    </flags>

  </module>

</bmforth-manifest>
```

## Element Reference

### `<bmforth-manifest>`

Root element. The `version` attribute specifies the manifest schema version.

### `<module>`

| Attribute | Required | Description |
|-----------|----------|-------------|
| `name`    | Yes      | Module name, matches the `USING` token (e.g., `USING RTL8139`) |
| `version` | Yes      | Semantic version: `MAJOR.MINOR.PATCH` |

### `<requires>/<use>`

Declares a dependency on another module.

| Attribute | Required | Description |
|-----------|----------|-------------|
| `module`  | Yes      | Name of the required module |
| `version` | No       | Version constraint: `>=X.Y.Z`, `=X.Y.Z`, `>=X.Y` |

Dependencies are loaded in declaration order before this module's definitions.

### `<definitions>/<use>`

Lists Forth source files to load, in order.

| Attribute | Required | Description |
|-----------|----------|-------------|
| `file`    | Yes      | Path to `.fth` file, relative to `forth/dict/` |

### `<logic>`

Inline Forth source code, wrapped in `CDATA` to avoid XML escaping issues. Loaded after all `<definitions>` files.

### `<exports>/<word>`

Documents the public API. Used by tools for validation and documentation generation. Not enforced at runtime.

| Attribute     | Required | Description |
|---------------|----------|-------------|
| `name`        | Yes      | Forth word name |
| `stack`       | Yes      | Stack effect notation: `( inputs -- outputs )` |
| `description` | No       | Human-readable description |

### `<pci-id>`

Hardware identification for auto-detection.

| Attribute | Required | Description |
|-----------|----------|-------------|
| `vendor`  | Yes      | PCI vendor ID (hex, no `0x` prefix) |
| `device`  | Yes      | PCI device ID (hex, no `0x` prefix) |

## Processing Pipeline

```
                 ┌──────────────┐
                 │ manifest.xml │
                 └──────┬───────┘
                        │
                        ▼
              ┌───────────────────┐
              │  Manifest Parser  │
              │  (host-side tool) │
              └────────┬──────────┘
                       │
                       ▼
              ┌───────────────────┐
              │  Dependency       │
              │  Resolver         │──── Error if circular or missing
              └────────┬──────────┘
                       │
                       ▼
              ┌───────────────────┐
              │  Forth Script     │
              │  Generator        │
              └────────┬──────────┘
                       │
                       ▼
                ┌──────────────┐
                │  load.fth    │   ← Generated load script
                └──────┬───────┘
                       │
                       ▼
              ┌───────────────────┐
              │  Bare-Metal Forth USING    │
              │  (runtime loader) │
              └───────────────────┘
```

### Step 1: Parse Manifest

Read the XML, validate against the schema, extract module metadata.

### Step 2: Resolve Dependencies

Build a dependency graph. Topologically sort modules. Detect:
- Missing dependencies
- Circular dependencies
- Version conflicts

### Step 3: Generate Forth Load Script

Output a `.fth` file that, when executed by Bare-Metal Forth, loads modules in dependency order:

```forth
\ Auto-generated by manifest processor
\ Module: RTL8139 v0.1.0

\ Load dependencies first
USING HARDWARE

\ Load module definitions
S" forth/dict/hardware.fth" INCLUDED
S" forth/dict/rtl8139.fth" INCLUDED

\ Register in dictionary system
S" RTL8139" 0 1 0 DICT-REGISTER
```

### Step 4: Runtime Loading

Bare-Metal Forth executes the generated script using its existing `USING` mechanism and dictionary system.

## Relationship to dict_system.fth

The manifest system is a **superset** of what `dict_system.fth` provides:

| Feature | dict_system.fth | Manifest System |
|---------|----------------|-----------------|
| Load module at runtime | `USING RTL8139` | Same (generated code calls `USING`) |
| Dependency declaration | Manual (comments) | `<requires>` element, auto-resolved |
| Version tracking | `DICT-VERSION` word | `version` attribute, constraint checking |
| API documentation | Forth comments | `<exports>` element, machine-readable |
| Hardware auto-detect | Manual `PCI-SCAN` | `<pci-id>`, matchable by tools |

## Example: Graphics Subsystem

A module that composes multiple lower-level modules:

```xml
<bmforth-manifest version="1.0">
  <module name="GRAPHICS" version="0.1.0">
    <description>Graphics subsystem with text and pixel modes</description>

    <requires>
      <use module="HARDWARE" version=">=0.1.0"/>
    </requires>

    <definitions>
      <use file="vga_text.fth"/>
      <use file="vga_mode13.fth"/>
    </definitions>

    <logic><![CDATA[
      \ High-level graphics words that combine text and pixel modes

      VARIABLE GFX-MODE   0 GFX-MODE !   \ 0=text, 1=mode13h

      : TEXT-MODE  ( -- )
          0 GFX-MODE !
          VGA-TEXT-INIT
      ;

      : PIXEL-MODE  ( -- )
          1 GFX-MODE !
          VGA-MODE13-INIT
      ;

      : PLOT  ( x y color -- )
          GFX-MODE @ 0= IF
              DROP 2DROP  \ No pixel plotting in text mode
          ELSE
              VGA-PLOT
          THEN
      ;
    ]]></logic>

    <exports>
      <word name="TEXT-MODE"  stack="( -- )"            description="Switch to 80x25 text mode"/>
      <word name="PIXEL-MODE" stack="( -- )"            description="Switch to 320x200 pixel mode"/>
      <word name="PLOT"       stack="( x y color -- )"  description="Plot a pixel (pixel mode only)"/>
    </exports>
  </module>
</bmforth-manifest>
```

## Implementation Status

| Component | Status |
|-----------|--------|
| Manifest XML schema | **Designed** (this document) |
| dict_system.fth runtime | **Implemented** (forth/dict/dict_system.fth) |
| HARDWARE dictionary | **Implemented** (forth/dict/hardware.fth) |
| RTL8139 example driver | **Implemented** (forth/dict/rtl8139.fth) |
| Manifest parser tool | Planned (Phase 2) |
| Dependency resolver | Planned (Phase 2) |
| Forth script generator | Planned (Phase 2) |
| PCI auto-detect integration | Planned (Phase 3) |

## Design Rationale

**Why XML?** The manifest format needs to be:
1. Parseable by simple host-side tools (Python, C)
2. Able to embed arbitrary Forth code (CDATA sections)
3. Human-editable with standard editors
4. Validatable against a schema

XML satisfies all four. JSON cannot cleanly embed multiline code. YAML has whitespace sensitivity issues with Forth's significant spacing. TOML lacks nested structure depth. XML with CDATA is the pragmatic choice for a system that mixes structured metadata with embedded source code.

**Why not parse XML at runtime?** Bare-Metal Forth runs on bare metal with ~320KB of dictionary space. An XML parser would consume precious memory and add complexity to the runtime. The manifest processor runs on the host machine where resources are abundant, and outputs compact Forth that the runtime can execute directly.
