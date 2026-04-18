#!/usr/bin/env python3
"""
disk-survey-viz.py - Parse ForthOS DISK-SURVEY output and generate visualizations.

Produces:
  1. An interactive HTML dashboard (Approach A) - Chart.js, self-contained
  2. Static matplotlib PNG charts (Approach B) - saved to diagrams/

Usage:
    python3 tools/disk-survey-viz.py disk-survey.txt

Outputs:
    diagrams/disk-survey-dashboard.html
    diagrams/disk-partition-map.png
    diagrams/disk-bloat-treemap.png
    diagrams/disk-architecture.png
    diagrams/disk-sovereignty-funnel.png
    diagrams/disk-duplication-top30.png
    diagrams/disk-classification-gap.png
"""

import re
import sys
import json
import os
from collections import Counter, defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_disk_survey(filepath):
    """Parse disk-survey.txt into structured data."""
    data = {
        'partitions': [],
        'summary': {},
        'binaries': [],          # list of (filename, classification) tuples
        'total_files': 0,
    }

    lines = Path(filepath).read_text(errors='replace').splitlines()

    # --- Phase 1: Find partition info (first occurrence) ---
    in_partitions = False
    for line in lines:
        if line.strip() == '=== Partitions ===':
            in_partitions = True
            continue
        if in_partitions:
            m = re.match(r'P(\d+)\s*:\s*(\S+)\s+([0-9A-Fa-f]+)', line)
            if m:
                data['partitions'].append({
                    'index': int(m.group(1)),
                    'type': m.group(2),
                    'lba': int(m.group(3), 16),
                })
            elif 'partitions found' in line:
                in_partitions = False
                break

    # --- Phase 2: Extract summary from first occurrence ---
    for line in lines:
        if line.startswith('Win drivers'):
            m = re.search(r'(\d+)', line)
            if m:
                data['summary']['win_drivers'] = int(m.group(1))
        elif line.startswith('Win libs'):
            m = re.search(r'(\d+)', line)
            if m:
                data['summary']['win_libs'] = int(m.group(1))
        elif line.startswith('Win exe'):
            m = re.search(r'(\d+)', line)
            if m:
                data['summary']['win_exe'] = int(m.group(1))
        elif line.startswith('UEFI'):
            m = re.search(r'(\d+)', line)
            if m:
                data['summary']['uefi'] = int(m.group(1))
        elif line.startswith('DOS'):
            m = re.search(r'(\d+)', line)
            if m:
                data['summary']['dos'] = int(m.group(1))
        elif line.startswith('Linux drivers'):
            m = re.search(r'(\d+)', line)
            if m:
                data['summary']['linux_drivers'] = int(m.group(1))
        elif line.startswith('Linux libs'):
            m = re.search(r'(\d+)', line)
            if m:
                data['summary']['linux_libs'] = int(m.group(1))
        elif line.startswith('Total files'):
            m = re.search(r'(\d+)', line)
            if m:
                data['total_files'] = int(m.group(1))
        elif line.strip() == '=== Binary Report ===':
            break

    # --- Phase 3: Parse Binary Report section ---
    binary_start = None
    for i, line in enumerate(lines):
        if line.strip() == '=== Binary Report ===':
            binary_start = i + 1
            break

    if binary_start is None:
        print("WARNING: No '=== Binary Report ===' section found", file=sys.stderr)
        return data

    skip_patterns = re.compile(
        r'^(===|---|NTFS at|FAT32 at|P\d|Scanning|Records:|MFT |'
        r'\d+ partitions|Root:|Subdir|ok |\.+$|$)'
    )

    for line in lines[binary_start:]:
        line = line.rstrip()
        if not line or skip_patterns.match(line):
            continue

        # Try to extract classification tag
        # v1 formats: "filename PE AMD64 console" / "filename unknown"
        # v2 formats: "filename unk:XXYYZZ" / "filename PE-res" /
        #             "filename ELF-res" / "filename res:XXYYZZ"
        classification = ''
        m = re.match(
            r'^\.?(.+?)\s+'
            r'(PE .+|ELF .+|unknown|unk:[0-9A-Fa-f]+|'
            r'PE-res|ELF-res|res:[0-9A-Fa-f]+)\s*$', line)
        if m:
            filename = m.group(1).strip()
            classification = m.group(2).strip()
        else:
            # No classification tag - unclassified (resident or read-fail)
            filename = line.strip().lstrip('.')
            classification = 'unclassified'

        if filename and not filename.startswith('=') and not filename.startswith('---'):
            data['binaries'].append((filename, classification))

    return data


def analyze(data):
    """Compute derived statistics from parsed data."""
    stats = {}

    # Architecture + subsystem breakdown
    arch_sub = Counter()
    for _, cls in data['binaries']:
        arch_sub[cls] += 1
    stats['classification_counts'] = dict(arch_sub.most_common())

    # Simplified architecture groups
    arch_groups = Counter()
    for cls, count in arch_sub.items():
        if 'AMD64' in cls or 'ARM64' in cls:
            arch_groups['AMD64/ARM64'] += count
        elif 'x86' in cls or ('ARM' in cls and 'ARM64' not in cls
                              and 'AArch64' not in cls):
            arch_groups['x86/ARM'] += count
        elif 'ELF' in cls or cls == 'ELF-res':
            arch_groups['ELF'] += count
        elif cls == 'unknown' or cls.startswith('unk:'):
            arch_groups['Unknown (non-PE/ELF)'] += count
        elif cls == 'unclassified':
            arch_groups['Unclassified'] += count
        elif cls == 'PE-res' or cls.startswith('res:'):
            arch_groups['MFT-resident'] += count
        else:
            arch_groups['Other'] += count
    stats['arch_groups'] = dict(arch_groups.most_common())

    # Extension breakdown
    ext_counts = Counter()
    for fname, _ in data['binaries']:
        m = re.search(r'\.([a-zA-Z0-9]+)$', fname)
        if m:
            ext_counts['.' + m.group(1).lower()] += 1
        else:
            ext_counts['(no ext)'] += 1
    stats['ext_counts'] = dict(ext_counts.most_common())

    # Duplication: filenames appearing multiple times
    name_counts = Counter()
    for fname, _ in data['binaries']:
        name_counts[fname.lower()] += 1
    top_dupes = name_counts.most_common(30)
    stats['top_duplicates'] = top_dupes

    # Extension by architecture (for treemap coloring)
    ext_by_arch = defaultdict(lambda: Counter())
    for fname, cls in data['binaries']:
        m = re.search(r'\.([a-zA-Z0-9]+)$', fname)
        ext = '.' + m.group(1).lower() if m else '(no ext)'
        if 'AMD64' in cls:
            ext_by_arch[ext]['AMD64'] += 1
        elif 'x86' in cls:
            ext_by_arch[ext]['x86'] += 1
        else:
            ext_by_arch[ext]['other'] += 1
    stats['ext_by_arch'] = {k: dict(v) for k, v in ext_by_arch.items()}

    # Classification detail for the gap panel
    cls_detail = {
        'pe_classified': 0,
        'elf_classified': 0,
        'unknown_tag': 0,
        'unclassified_resident': 0,
        'pe_resident': 0,
        'elf_resident': 0,
        'res_hex': 0,
        'unk_hex': 0,
    }
    for cls, count in arch_sub.items():
        if cls.startswith('PE '):
            cls_detail['pe_classified'] += count
        elif cls.startswith('ELF '):
            cls_detail['elf_classified'] += count
        elif cls == 'unknown':
            cls_detail['unknown_tag'] += count
        elif cls == 'PE-res':
            cls_detail['pe_resident'] += count
        elif cls == 'ELF-res':
            cls_detail['elf_resident'] += count
        elif cls.startswith('res:'):
            cls_detail['res_hex'] += count
        elif cls.startswith('unk:'):
            cls_detail['unk_hex'] += count
        elif cls == 'unclassified':
            cls_detail['unclassified_resident'] += count
    stats['classification_detail'] = cls_detail

    # Unclassified breakdown by extension
    uncls_ext = Counter()
    unknown_ext = Counter()
    for fname, cls in data['binaries']:
        m = re.search(r'\.([a-zA-Z0-9]+)$', fname)
        ext = '.' + m.group(1).lower() if m else '(no ext)'
        if cls == 'unclassified':
            uncls_ext[ext] += 1
        elif cls == 'unknown' or cls.startswith('unk:'):
            unknown_ext[ext] += 1
        elif cls.startswith('res:') or cls == 'PE-res' or cls == 'ELF-res':
            uncls_ext[ext] += 1  # resident files grouped with unclassified
    stats['unclassified_by_ext'] = dict(uncls_ext.most_common(10))
    stats['unknown_by_ext'] = dict(unknown_ext.most_common(10))

    # Sovereignty funnel
    total_files = data['total_files'] or sum(data['summary'].values())
    total_binaries = len(data['binaries'])
    total_drivers = sum(1 for _, c in data['binaries'] if 'driver' in c)
    x86_drivers = sum(1 for _, c in data['binaries'] if 'x86 driver' in c)
    stats['funnel'] = {
        'total_files': total_files,
        'total_binaries': total_binaries,
        'total_drivers': total_drivers,
        'x86_drivers': x86_drivers,
    }

    # Detailed architecture + subsystem for donut chart
    detailed_arch = Counter()
    for cls, count in arch_sub.items():
        if cls == 'unclassified':
            detailed_arch['Unclassified'] += count
        elif cls == 'unknown':
            detailed_arch['Unknown (not PE/ELF)'] += count
        elif cls.startswith('unk:'):
            detailed_arch['unk: (hex triage)'] += count
        elif cls == 'PE-res':
            detailed_arch['PE-res (MFT-resident)'] += count
        elif cls == 'ELF-res':
            detailed_arch['ELF-res (MFT-resident)'] += count
        elif cls.startswith('res:'):
            detailed_arch['res: (resident other)'] += count
        elif 'PE AMD64 driver' in cls:
            detailed_arch['AMD64 Driver'] += count
        elif 'PE x86 driver' in cls:
            detailed_arch['x86 Driver'] += count
        elif 'PE AMD64 GUI' in cls:
            detailed_arch['AMD64 GUI'] += count
        elif 'PE AMD64 console' in cls:
            detailed_arch['AMD64 Console'] += count
        elif 'PE x86 GUI' in cls:
            detailed_arch['x86 GUI'] += count
        elif 'PE x86 console' in cls:
            detailed_arch['x86 Console'] += count
        elif 'PE AMD64' in cls:
            detailed_arch['AMD64 Other'] += count
        elif 'PE x86' in cls:
            detailed_arch['x86 Other'] += count
        elif 'PE ARM64' in cls:
            detailed_arch['ARM64 (PE)'] += count
        elif 'PE ARM' in cls:
            detailed_arch['ARM (PE)'] += count
        elif 'PE unk' in cls:
            detailed_arch['PE Unknown Arch'] += count
        elif 'ELF' in cls:
            detailed_arch['ELF (Linux)'] += count
        else:
            detailed_arch['Other'] += count
    stats['detailed_arch'] = dict(detailed_arch.most_common())

    return stats


# ---------------------------------------------------------------------------
# HTML Dashboard (Approach A)
# ---------------------------------------------------------------------------

def generate_html(data, stats, output_path):
    """Generate a self-contained interactive HTML dashboard."""

    partitions_json = json.dumps(data['partitions'])
    ext_counts_json = json.dumps(stats['ext_counts'])
    ext_by_arch_json = json.dumps(stats['ext_by_arch'])
    detailed_arch_json = json.dumps(stats['detailed_arch'])
    top_dupes_json = json.dumps(stats['top_duplicates'])
    funnel_json = json.dumps(stats['funnel'])
    cls_detail_json = json.dumps(stats['classification_detail'])
    uncls_ext_json = json.dumps(stats['unclassified_by_ext'])
    unknown_ext_json = json.dumps(stats['unknown_by_ext'])
    total_binaries = len(data['binaries'])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ForthOS Disk Survey Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Courier New', monospace;
    background: #0a0a0f;
    color: #c0c0c0;
    padding: 20px;
  }}
  h1 {{
    text-align: center;
    color: #00ff88;
    font-size: 1.8em;
    margin-bottom: 5px;
  }}
  .subtitle {{
    text-align: center;
    color: #607080;
    margin-bottom: 25px;
    font-size: 0.9em;
  }}
  .grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    max-width: 1400px;
    margin: 0 auto;
  }}
  .panel {{
    background: #12121a;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    padding: 18px;
  }}
  .panel-full {{ grid-column: 1 / -1; }}
  .panel h2 {{
    color: #00cc66;
    font-size: 1.05em;
    margin-bottom: 12px;
    border-bottom: 1px solid #2a2a3a;
    padding-bottom: 6px;
  }}
  .panel h2 .num {{
    color: #ff8844;
    float: right;
    font-size: 0.85em;
  }}
  .partition-bar {{
    display: flex;
    height: 50px;
    border-radius: 4px;
    overflow: hidden;
    margin: 10px 0;
  }}
  .partition-bar div {{
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.7em;
    color: #fff;
    text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
    position: relative;
    min-width: 2px;
  }}
  .partition-bar div:hover {{
    opacity: 0.85;
    cursor: pointer;
  }}
  .part-legend {{
    display: flex;
    gap: 15px;
    flex-wrap: wrap;
    margin-top: 8px;
    font-size: 0.8em;
  }}
  .funnel-row {{
    display: flex;
    align-items: center;
    margin: 6px 0;
  }}
  .funnel-bar {{
    height: 28px;
    border-radius: 3px;
    display: flex;
    align-items: center;
    padding-left: 10px;
    color: #fff;
    font-size: 0.8em;
    min-width: 40px;
    transition: width 0.5s;
  }}
  .funnel-label {{
    min-width: 200px;
    font-size: 0.8em;
    color: #90a0b0;
  }}
  .chart-container {{
    position: relative;
    width: 100%;
  }}
  .chart-container canvas {{
    max-height: 400px;
  }}
  table.gap-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8em;
    margin-top: 10px;
  }}
  table.gap-table th {{
    text-align: left;
    color: #00cc66;
    border-bottom: 1px solid #2a2a3a;
    padding: 5px 8px;
  }}
  table.gap-table td {{
    padding: 5px 8px;
    border-bottom: 1px solid #1a1a2a;
  }}
  table.gap-table td.num {{
    text-align: right;
    color: #ff8844;
    font-weight: bold;
  }}
  table.gap-table td.fix {{
    color: #4488ff;
    font-size: 0.9em;
  }}
  .insight {{
    background: #1a1a25;
    border-left: 3px solid #ff8844;
    padding: 10px 14px;
    margin-top: 12px;
    font-size: 0.8em;
    line-height: 1.5;
    color: #a0a0b0;
  }}
  .insight strong {{ color: #ff8844; }}
  .ext-breakdown {{
    display: flex;
    gap: 20px;
    margin-top: 10px;
  }}
  .ext-breakdown div {{
    flex: 1;
  }}
  .ext-breakdown h3 {{
    color: #90a0b0;
    font-size: 0.85em;
    margin-bottom: 5px;
  }}
  .ext-breakdown ul {{
    list-style: none;
    font-size: 0.8em;
  }}
  .ext-breakdown li {{
    padding: 2px 0;
  }}
  .ext-breakdown li .cnt {{
    color: #ff8844;
    float: right;
  }}
</style>
</head>
<body>

<h1>ForthOS Disk Survey</h1>
<p class="subtitle" id="subtitle"></p>

<div class="grid">

  <!-- Panel 1: Partition Map -->
  <div class="panel panel-full">
    <h2>Disk Partition Layout <span class="num" id="part-count-label"></span></h2>
    <div id="partition-bar" class="partition-bar"></div>
    <div id="partition-legend" class="part-legend"></div>
  </div>

  <!-- Panel 2: Bloat Treemap (extension breakdown) -->
  <div class="panel">
    <h2>Binary Landscape by Extension</h2>
    <div class="chart-container">
      <canvas id="ext-chart"></canvas>
    </div>
  </div>

  <!-- Panel 3: Architecture Distribution -->
  <div class="panel">
    <h2>Architecture Distribution</h2>
    <div class="chart-container">
      <canvas id="arch-chart"></canvas>
    </div>
  </div>

  <!-- Panel 4: Sovereignty Funnel -->
  <div class="panel panel-full">
    <h2>The Sovereignty Funnel &mdash; What You Actually Need</h2>
    <div id="funnel"></div>
    <div class="insight">
      <strong>What this means:</strong> Out of everything Windows installed on this drive,
      only a tiny fraction represents hardware interaction code. ForthOS aims to replace
      those layers with auditable, sovereign Forth vocabularies &mdash; code you can read
      in its entirety.
    </div>
  </div>

  <!-- Panel 5: Duplication Top 30 -->
  <div class="panel">
    <h2>Top 30 Most Duplicated Files</h2>
    <div class="chart-container">
      <canvas id="dupe-chart"></canvas>
    </div>
  </div>

  <!-- Panel 6: Classification Gap -->
  <div class="panel">
    <h2>Classification Coverage</h2>
    <div class="chart-container">
      <canvas id="gap-chart"></canvas>
    </div>
    <table class="gap-table" id="gap-table">
      <thead><tr>
        <th>Category</th><th>Count</th><th>Root Cause</th><th>ForthOS Fix</th>
      </tr></thead>
      <tbody id="gap-tbody"></tbody>
    </table>
    <div class="ext-breakdown" id="ext-breakdown"></div>
  </div>

</div>

<script>
// --- Data (all from local disk-survey.txt, not user input) ---
const partitions = {partitions_json};
const extCounts = {ext_counts_json};
const extByArch = {ext_by_arch_json};
const detailedArch = {detailed_arch_json};
const topDupes = {top_dupes_json};
const funnel = {funnel_json};
const clsDetail = {cls_detail_json};
const unclsExt = {uncls_ext_json};
const unknownExt = {unknown_ext_json};
const totalBinaries = {total_binaries};

// --- Subtitle ---
document.getElementById('subtitle').textContent =
  'HP 15-bs0xx \\u2014 Bare-metal binary audit via AHCI + NTFS + FAT32 \\u2014 ' +
  totalBinaries.toLocaleString() + ' binaries classified';

// --- Colors ---
const ARCH_COLORS = {{
  'x86 GUI': '#1565C0', 'x86 Console': '#42A5F5', 'x86 Driver': '#0D47A1',
  'x86 Other': '#90CAF9',
  'AMD64 GUI': '#C62828', 'AMD64 Console': '#EF5350', 'AMD64 Driver': '#B71C1C',
  'AMD64 Other': '#EF9A9A',
  'ELF (Linux)': '#7B1FA2',
  'PE Unknown Arch': '#455A64',
  'Unknown (not PE/ELF)': '#37474F',
  'Unclassified (resident)': '#263238',
  'Other': '#546E7A',
}};

// --- Helper: create element with text ---
function el(tag, text, styles) {{
  const e = document.createElement(tag);
  if (text) e.textContent = text;
  if (styles) Object.assign(e.style, styles);
  return e;
}}

// --- Panel 1: Partition Map ---
(function() {{
  const bar = document.getElementById('partition-bar');
  const legend = document.getElementById('partition-legend');
  document.getElementById('part-count-label').textContent =
    partitions.length + ' partitions';
  if (!partitions.length) return;

  const maxLBA = Math.max(...partitions.map(p => p.lba)) * 1.05;
  const parts = [];
  for (let i = 0; i < partitions.length; i++) {{
    const start = partitions[i].lba;
    const end = (i + 1 < partitions.length) ? partitions[i+1].lba : maxLBA;
    const ptype = partitions[i].type.replace('LBA', '');
    parts.push({{ start, end, size: end - start, ptype, index: partitions[i].index }});
  }}

  const totalSize = parts.reduce((s, p) => s + p.size, 0);
  const typeColors = {{
    'FAT32': '#2196F3', 'NTFS': '#4CAF50', 'Recovery': '#FF9800', 'Unknown': '#607D8B'
  }};

  parts.forEach(p => {{
    const pct = Math.max((p.size / totalSize) * 100, 1.5);
    const color = typeColors[p.ptype] || '#607D8B';
    const div = document.createElement('div');
    div.style.width = pct + '%';
    div.style.background = color;
    div.title = 'P' + p.index + ': ' + p.ptype +
      '\\nLBA: 0x' + p.start.toString(16).toUpperCase() +
      '\\nSize: ' + (p.size * 512 / 1e9).toFixed(1) + ' GB';
    div.textContent = pct > 5 ? ('P' + p.index + ' ' + p.ptype) : ('P' + p.index);
    bar.appendChild(div);
  }});

  parts.forEach(p => {{
    const color = typeColors[p.ptype] || '#607D8B';
    const span = document.createElement('span');
    span.style.display = 'inline-flex';
    span.style.alignItems = 'center';
    const swatch = document.createElement('span');
    swatch.style.cssText = 'display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:5px;background:' + color;
    span.appendChild(swatch);
    span.appendChild(document.createTextNode(
      'P' + p.index + ': ' + p.ptype + ' (LBA 0x' + p.start.toString(16).toUpperCase() + ')'
    ));
    legend.appendChild(span);
  }});
}})();

// --- Panel 2: Extension Breakdown (horizontal bar) ---
(function() {{
  const entries = Object.entries(extCounts).slice(0, 15);
  const labels = entries.map(e => e[0]);
  const values = entries.map(e => e[1]);

  const bgColors = labels.map(ext => {{
    const arch = extByArch[ext] || {{}};
    const amd = arch['AMD64'] || 0;
    const x86 = arch['x86'] || 0;
    const other = arch['other'] || 0;
    if (amd > x86 && amd > other) return '#EF5350';
    if (x86 > amd && x86 > other) return '#42A5F5';
    return '#607D8B';
  }});

  new Chart(document.getElementById('ext-chart'), {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [{{ data: values, backgroundColor: bgColors, borderWidth: 0 }}]
    }},
    options: {{
      indexAxis: 'y',
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            afterLabel: function(ctx) {{
              const ext = ctx.label;
              const arch = extByArch[ext] || {{}};
              let s = '';
              if (arch.AMD64) s += 'AMD64: ' + arch.AMD64.toLocaleString() + '\\n';
              if (arch.x86) s += 'x86: ' + arch.x86.toLocaleString() + '\\n';
              if (arch.other) s += 'Other/Unknown: ' + arch.other.toLocaleString();
              return s;
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{ color: '#888', callback: v => v.toLocaleString() }},
          grid: {{ color: '#1a1a2a' }}
        }},
        y: {{
          ticks: {{ color: '#c0c0c0', font: {{ family: 'Courier New' }} }},
          grid: {{ display: false }}
        }}
      }}
    }}
  }});
}})();

// --- Panel 3: Architecture Donut ---
(function() {{
  const labels = Object.keys(detailedArch);
  const values = Object.values(detailedArch);
  const colors = labels.map(l => ARCH_COLORS[l] || '#546E7A');

  new Chart(document.getElementById('arch-chart'), {{
    type: 'doughnut',
    data: {{
      labels: labels,
      datasets: [{{
        data: values,
        backgroundColor: colors,
        borderColor: '#12121a',
        borderWidth: 2
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{
          position: 'right',
          labels: {{
            color: '#a0a0b0',
            font: {{ family: 'Courier New', size: 10 }},
            padding: 6,
            usePointStyle: true,
            pointStyle: 'rectRounded'
          }}
        }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{
              const total = ctx.dataset.data.reduce((a,b) => a+b, 0);
              const pct = ((ctx.parsed / total) * 100).toFixed(1);
              return ctx.label + ': ' + ctx.parsed.toLocaleString() + ' (' + pct + '%)';
            }}
          }}
        }}
      }}
    }}
  }});
}})();

// --- Panel 4: Sovereignty Funnel ---
(function() {{
  const container = document.getElementById('funnel');
  const items = [
    {{ label: 'Total files on disk', value: funnel.total_files, color: '#37474F' }},
    {{ label: 'Binaries (PE/ELF extensions)', value: funnel.total_binaries, color: '#455A64' }},
    {{ label: 'Hardware drivers (.sys/.drv)', value: funnel.total_drivers, color: '#FF9800' }},
    {{ label: 'x86 drivers (ForthOS target arch)', value: funnel.x86_drivers, color: '#4CAF50' }},
  ];
  const maxVal = items[0].value;

  items.forEach((item, i) => {{
    const row = document.createElement('div');
    row.className = 'funnel-row';
    const pct = Math.max((item.value / maxVal) * 100, 3);
    const ratio = i > 0
      ? ' (' + (item.value / items[0].value * 100).toFixed(item.value < 1000 ? 3 : 1) + '%)'
      : '';

    const labelDiv = document.createElement('div');
    labelDiv.className = 'funnel-label';
    labelDiv.textContent = item.label;

    const barDiv = document.createElement('div');
    barDiv.className = 'funnel-bar';
    barDiv.style.width = pct + '%';
    barDiv.style.background = item.color;
    barDiv.textContent = item.value.toLocaleString() + ratio;

    row.appendChild(labelDiv);
    row.appendChild(barDiv);
    container.appendChild(row);
  }});
}})();

// --- Panel 5: Duplication Top 30 ---
(function() {{
  const labels = topDupes.map(d => d[0].length > 30 ? d[0].slice(0, 27) + '...' : d[0]);
  const values = topDupes.map(d => d[1]);

  new Chart(document.getElementById('dupe-chart'), {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [{{
        data: values,
        backgroundColor: '#FF9800',
        borderWidth: 0
      }}]
    }},
    options: {{
      indexAxis: 'y',
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            title: function(ctx) {{ return topDupes[ctx[0].dataIndex][0]; }}
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{ color: '#888' }},
          grid: {{ color: '#1a1a2a' }}
        }},
        y: {{
          ticks: {{ color: '#c0c0c0', font: {{ family: 'Courier New', size: 9 }} }},
          grid: {{ display: false }}
        }}
      }}
    }}
  }});
}})();

// --- Panel 6: Classification Gap ---
(function() {{
  const labels = ['PE Classified', 'ELF Classified', 'Unknown (no MZ/ELF)', 'Unclassified (resident)'];
  const values = [
    clsDetail.pe_classified,
    clsDetail.elf_classified,
    clsDetail.unknown_tag,
    clsDetail.unclassified_resident
  ];
  const colors = ['#4CAF50', '#7B1FA2', '#FF9800', '#37474F'];

  new Chart(document.getElementById('gap-chart'), {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [{{ data: values, backgroundColor: colors, borderWidth: 0 }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{
          ticks: {{ color: '#a0a0b0', font: {{ size: 9 }} }},
          grid: {{ display: false }}
        }},
        y: {{
          ticks: {{ color: '#888', callback: v => v.toLocaleString() }},
          grid: {{ color: '#1a1a2a' }}
        }}
      }}
    }}
  }});

  // Gap detail table (safe DOM construction)
  const tbody = document.getElementById('gap-tbody');
  const gapRows = [
    ['Unclassified (resident)', clsDetail.unclassified_resident,
     'Data stored inline in MFT record (no disk clusters)',
     'Read $DATA attribute from MFT buffer directly'],
    ['Unknown (no PE/ELF)', clsDetail.unknown_tag,
     'First sector lacks MZ/ELF magic (NTFS-compressed, raw .com, page files)',
     'Add NTFS decompression; print first 4 bytes for triage'],
    ['PE sub?', 67,
     'PE subsystem not native/GUI/console (EFI app, POSIX, etc.)',
     'Extend subsystem table: EFI_APP=10, EFI_BOOT=11, EFI_RT=12'],
    ['PE/ELF unk-arch/mach', 82,
     'Machine type not i386/AMD64/x86/x86-64',
     'Add ARM (0x28), AArch64 (0xB7), IA-64 (0x200)'],
  ];
  gapRows.forEach(r => {{
    const tr = document.createElement('tr');
    const td0 = document.createElement('td');
    td0.textContent = r[0];
    const td1 = document.createElement('td');
    td1.className = 'num';
    td1.textContent = typeof r[1] === 'number' ? r[1].toLocaleString() : r[1];
    const td2 = document.createElement('td');
    td2.textContent = r[2];
    const td3 = document.createElement('td');
    td3.className = 'fix';
    td3.textContent = r[3];
    tr.appendChild(td0);
    tr.appendChild(td1);
    tr.appendChild(td2);
    tr.appendChild(td3);
    tbody.appendChild(tr);
  }});

  // Extension breakdowns (safe DOM construction)
  const container = document.getElementById('ext-breakdown');
  function makeList(title, data) {{
    const div = document.createElement('div');
    const h3 = document.createElement('h3');
    h3.textContent = title;
    div.appendChild(h3);
    const ul = document.createElement('ul');
    Object.entries(data).forEach(function(pair) {{
      const li = document.createElement('li');
      li.appendChild(document.createTextNode(pair[0] + ' '));
      const cnt = document.createElement('span');
      cnt.className = 'cnt';
      cnt.textContent = pair[1].toLocaleString();
      li.appendChild(cnt);
      ul.appendChild(li);
    }});
    div.appendChild(ul);
    container.appendChild(div);
  }}
  makeList('Unclassified by Extension', unclsExt);
  makeList('Unknown by Extension', unknownExt);
}})();
</script>

</body>
</html>"""

    Path(output_path).write_text(html)
    print(f"  HTML dashboard: {output_path}")


# ---------------------------------------------------------------------------
# Matplotlib charts (Approach B)
# ---------------------------------------------------------------------------

def generate_matplotlib(data, stats, output_dir):
    """Generate static PNG charts using matplotlib."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("  WARNING: matplotlib not installed, skipping PNG charts", file=sys.stderr)
        return

    os.makedirs(output_dir, exist_ok=True)
    plt.rcParams.update({
        'figure.facecolor': '#0a0a0f',
        'axes.facecolor': '#12121a',
        'axes.edgecolor': '#2a2a3a',
        'text.color': '#c0c0c0',
        'xtick.color': '#888888',
        'ytick.color': '#888888',
        'axes.labelcolor': '#a0a0b0',
        'font.family': 'monospace',
        'font.size': 10,
    })

    # --- Chart 1: Partition Map ---
    fig, ax = plt.subplots(figsize=(14, 2.5))
    parts = data['partitions']
    if parts:
        max_lba = max(p['lba'] for p in parts) * 1.05
        type_colors = {'FAT32': '#2196F3', 'NTFS': '#4CAF50', 'Recovery': '#FF9800', 'Unknown': '#607D8B'}
        left = 0
        for i, p in enumerate(parts):
            ptype = p['type'].replace('LBA', '')
            start = p['lba']
            end = parts[i+1]['lba'] if i+1 < len(parts) else max_lba
            width = (end - start) / max_lba
            color = type_colors.get(ptype, '#607D8B')
            ax.barh(0, width, left=left, height=0.6, color=color,
                    edgecolor='#0a0a0f', linewidth=1)
            if width > 0.04:
                ax.text(left + width/2, 0, f'P{p["index"]}\n{ptype}',
                       ha='center', va='center', fontsize=8, color='white',
                       fontweight='bold')
            left += width

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, 0.5)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title('Disk Partition Layout', color='#00cc66', fontsize=13, pad=10)
    patches = [mpatches.Patch(color=c, label=l) for l, c in
               [('FAT32/EFI', '#2196F3'), ('NTFS', '#4CAF50'),
                ('Recovery', '#FF9800'), ('Unknown', '#607D8B')]]
    ax.legend(handles=patches, loc='upper right', fontsize=8,
             facecolor='#12121a', edgecolor='#2a2a3a', labelcolor='#a0a0b0')
    fig.tight_layout()
    fig.savefig(f'{output_dir}/disk-partition-map.png', dpi=150)
    plt.close()
    print(f"  PNG: {output_dir}/disk-partition-map.png")

    # --- Chart 2: Extension Breakdown ---
    fig, ax = plt.subplots(figsize=(10, 7))
    entries = list(stats['ext_counts'].items())[:15]
    labels = [e[0] for e in entries][::-1]
    values = [e[1] for e in entries][::-1]
    ext_arch = stats['ext_by_arch']
    bar_colors = []
    for ext in labels:
        arch = ext_arch.get(ext, {})
        amd = arch.get('AMD64', 0)
        x86 = arch.get('x86', 0)
        other = arch.get('other', 0)
        if amd > x86 and amd > other:
            bar_colors.append('#EF5350')
        elif x86 > amd and x86 > other:
            bar_colors.append('#42A5F5')
        else:
            bar_colors.append('#607D8B')

    bars = ax.barh(range(len(labels)), values, color=bar_colors, edgecolor='none')
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_xlabel('Count')
    ax.set_title('Binary Landscape by Extension', color='#00cc66', fontsize=13, pad=10)
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + max(values)*0.01, bar.get_y() + bar.get_height()/2,
                f'{val:,}', va='center', fontsize=8, color='#888')
    patches = [mpatches.Patch(color='#EF5350', label='Mostly AMD64'),
               mpatches.Patch(color='#42A5F5', label='Mostly x86'),
               mpatches.Patch(color='#607D8B', label='Mixed/Unknown')]
    ax.legend(handles=patches, fontsize=8, facecolor='#12121a',
             edgecolor='#2a2a3a', labelcolor='#a0a0b0')
    fig.tight_layout()
    fig.savefig(f'{output_dir}/disk-bloat-treemap.png', dpi=150)
    plt.close()
    print(f"  PNG: {output_dir}/disk-bloat-treemap.png")

    # --- Chart 3: Architecture Donut ---
    fig, ax = plt.subplots(figsize=(10, 7))
    arch_data = stats['detailed_arch']
    arch_labels = list(arch_data.keys())
    arch_values = list(arch_data.values())
    arch_colors_list = [
        '#1565C0', '#42A5F5', '#0D47A1', '#90CAF9',
        '#C62828', '#EF5350', '#B71C1C', '#EF9A9A',
        '#7B1FA2', '#455A64', '#37474F', '#263238',
        '#546E7A', '#78909C',
    ]
    colors = arch_colors_list[:len(arch_labels)]
    wedges, _, _ = ax.pie(
        arch_values, labels=None, autopct='',
        colors=colors, startangle=90,
        pctdistance=0.8, wedgeprops={'edgecolor': '#0a0a0f', 'linewidth': 1.5}
    )
    centre_circle = plt.Circle((0, 0), 0.55, fc='#12121a')
    ax.add_artist(centre_circle)
    ax.set_title('Architecture Distribution', color='#00cc66', fontsize=13, pad=10)
    legend_labels = [f'{l} ({v:,})' for l, v in zip(arch_labels, arch_values)]
    ax.legend(wedges, legend_labels, loc='center left', bbox_to_anchor=(0.95, 0.5),
             fontsize=7, facecolor='#12121a', edgecolor='#2a2a3a', labelcolor='#a0a0b0')
    fig.tight_layout()
    fig.savefig(f'{output_dir}/disk-architecture.png', dpi=150)
    plt.close()
    print(f"  PNG: {output_dir}/disk-architecture.png")

    # --- Chart 4: Sovereignty Funnel ---
    fig, ax = plt.subplots(figsize=(12, 3.5))
    f = stats['funnel']
    items = [
        ('Total files on disk', f['total_files'], '#37474F'),
        ('Binaries (PE/ELF extensions)', f['total_binaries'], '#455A64'),
        ('Hardware drivers (.sys/.drv)', f['total_drivers'], '#FF9800'),
        ('x86 drivers (ForthOS target)', f['x86_drivers'], '#4CAF50'),
    ]
    max_val = items[0][1]
    y_positions = list(range(len(items)-1, -1, -1))

    for i, (label, val, color) in enumerate(items):
        width = max(val / max_val, 0.02)
        ax.barh(y_positions[i], width, height=0.6, color=color, edgecolor='none')
        pct = f' ({val/max_val*100:.3f}%)' if val < 10000 else f' ({val/max_val*100:.1f}%)'
        if i == 0:
            pct = ''
        ax.text(width + 0.01, y_positions[i], f'{val:,}{pct}',
                va='center', fontsize=9, color='#c0c0c0')

    ax.set_yticks(y_positions)
    ax.set_yticklabels([item[0] for item in items], fontsize=9)
    ax.set_xlim(0, 1.3)
    ax.set_xticks([])
    ax.set_title('The Sovereignty Funnel', color='#00cc66', fontsize=13, pad=10)
    fig.tight_layout()
    fig.savefig(f'{output_dir}/disk-sovereignty-funnel.png', dpi=150)
    plt.close()
    print(f"  PNG: {output_dir}/disk-sovereignty-funnel.png")

    # --- Chart 5: Duplication Top 30 ---
    fig, ax = plt.subplots(figsize=(10, 9))
    dupes = stats['top_duplicates']
    d_labels = [d[0][:35] + ('...' if len(d[0]) > 35 else '') for d in dupes][::-1]
    d_values = [d[1] for d in dupes][::-1]
    ax.barh(range(len(d_labels)), d_values, color='#FF9800', edgecolor='none')
    ax.set_yticks(range(len(d_labels)))
    ax.set_yticklabels(d_labels, fontsize=7)
    ax.set_xlabel('Copies on Disk')
    ax.set_title('Top 30 Most Duplicated Filenames', color='#00cc66', fontsize=13, pad=10)
    for i, val in enumerate(d_values):
        ax.text(val + max(d_values)*0.01, i, str(val), va='center', fontsize=7, color='#888')
    fig.tight_layout()
    fig.savefig(f'{output_dir}/disk-duplication-top30.png', dpi=150)
    plt.close()
    print(f"  PNG: {output_dir}/disk-duplication-top30.png")

    # --- Chart 6: Classification Gap ---
    fig, ax = plt.subplots(figsize=(10, 5))
    cd = stats['classification_detail']
    gap_labels = ['PE Classified', 'ELF Classified', 'Unknown\n(no MZ/ELF)', 'Unclassified\n(MFT-resident)']
    gap_values = [cd['pe_classified'], cd['elf_classified'],
                  cd['unknown_tag'], cd['unclassified_resident']]
    gap_colors = ['#4CAF50', '#7B1FA2', '#FF9800', '#37474F']
    bars = ax.bar(range(len(gap_labels)), gap_values, color=gap_colors, edgecolor='none')
    ax.set_xticks(range(len(gap_labels)))
    ax.set_xticklabels(gap_labels, fontsize=9)
    ax.set_ylabel('Count')
    ax.set_title('Classification Coverage', color='#00cc66', fontsize=13, pad=10)
    for bar, val in zip(bars, gap_values):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(gap_values)*0.01,
                    f'{val:,}', ha='center', fontsize=9, color='#c0c0c0')
    fig.tight_layout()
    fig.savefig(f'{output_dir}/disk-classification-gap.png', dpi=150)
    plt.close()
    print(f"  PNG: {output_dir}/disk-classification-gap.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <disk-survey.txt>", file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.isfile(filepath):
        print(f"Error: {filepath} not found", file=sys.stderr)
        sys.exit(1)

    # Determine output directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    output_dir = os.path.join(project_dir, 'diagrams')
    os.makedirs(output_dir, exist_ok=True)

    print(f"Parsing {filepath}...")
    data = parse_disk_survey(filepath)
    print(f"  Partitions: {len(data['partitions'])}")
    print(f"  Binaries: {len(data['binaries']):,}")
    print(f"  Total files: {data['total_files']:,}")

    print("Analyzing...")
    stats = analyze(data)

    print("Generating visualizations...")
    generate_html(data, stats, os.path.join(output_dir, 'disk-survey-dashboard.html'))
    generate_matplotlib(data, stats, output_dir)

    print("Done.")


if __name__ == '__main__':
    main()
