#!/usr/bin/env python3
"""QEMU port inventory, generated from the Makefile and tests/*.py
(TASK_PORT_REFUSAL_4C §3). No hand-kept port table.

For every test-* recipe: each TCP port a QEMU it starts will listen on, as
an offset from TEST_PORT_BASE, with its listen form and where it comes from.

- Recipe-launched QEMUs: from the recipe's -serial / -monitor / -netdev
  ...listen= text.
- Script-launched QEMUs: from the script's f-strings (`tcp::{X}`,
  `tcp:127.0.0.1:{X}`, `listen=:{X}`), with X resolved by Python's ast to
  "the port the recipe passed in, plus a constant", through assignments,
  function parameters and call sites.
- Loops: test-vocabs / test-gui (`+N+I`, I = position in *_ALL) and
  test-meta (`+off` from META_FIXTURES_ALL) give one entry per fixture.

Fails closed: a listen address it cannot resolve is an error.

  port_inventory.py            print the inventory as JSON
  port_inventory.py --check F  exit 1 if it differs from F (drift), if any
                               serial or monitor uses the tcp::P form, or
                               if a recipe in the table does not run
                               $(PORTS_FREE) --recipe <itself> (UNGUARDED)
A script that is absent (a private-owned script in a public clone) is
reported as SKIPPED and its committed entries are not compared.
"""
import ast, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMS = (('tcp:127.0.0.1:', 'tcp:127.0.0.1:P'), ('tcp::', 'tcp::P'), ('listen=:', 'listen=:P'))
ARGV = 'ARGV'


class Unresolved(Exception):
    pass


# ---------------- Makefile ----------------

def makefile():
    text = open(os.path.join(ROOT, 'Makefile')).read()
    lines = text.split('\n')
    joined, vars_, recipes = [], {}, {}
    buf, start = '', 0
    for i, ln in enumerate(lines, 1):
        if not buf:
            start = i
        if ln.endswith('\\'):
            buf += ln[:-1] + ' '
            continue
        joined.append((start, buf + ln))
        buf = ''
    cur = None
    for n, ln in joined:
        m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*\??=\s*(.*)$', ln)
        if m and not ln.startswith('\t'):
            vars_[m.group(1)] = m.group(2).strip()
        m = re.match(r'^(test-[a-z0-9-]+):', ln)
        if m:
            cur = m.group(1)
            recipes[cur] = []
            continue
        if ln.startswith('\t') and cur:
            recipes[cur].append((n, ln))
        elif ln.strip() and not ln.startswith('\t') and not ln.startswith('#'):
            cur = None
    return vars_, recipes


def mk_offset(expr, rvars):
    """Makefile port expression -> offset (int) or ('INDEX', base) for loops."""
    expr = expr.strip()
    m = re.fullmatch(r'\$\$\(\(\$\(TEST_PORT_BASE\)\+(\d+)\)\)', expr)
    if m:
        return int(m.group(1))
    if expr == '$(TEST_PORT_BASE)':
        return 0
    m = re.fullmatch(r'\$\$(\w+)', expr)
    if m and m.group(1) in rvars:
        return rvars[m.group(1)]
    raise Unresolved(f'Makefile port expression {expr!r}')


def recipe_vars(body):
    out = {}
    for _, ln in body:
        for m in re.finditer(r'\b(\w+)=\$\$\(\(\$\(TEST_PORT_BASE\)\+([^)]*)\)\)', ln):
            name, e = m.group(1), m.group(2)
            if re.fullmatch(r'\d+', e):
                out[name] = int(e)
            elif re.fullmatch(r'(\d+)\+I', e):
                out[name] = ('INDEX', int(e.split('+')[0]))
            elif e == '$$off':
                out[name] = ('OFF', 0)
            else:
                raise Unresolved(f'recipe variable {name}={e!r}')
    return out


# ---------------- scripts (ast) ----------------

class Script:
    def __init__(self, path, argmap):
        self.path = path
        self.argmap = argmap    # sys.argv index -> TEST_PORT_BASE offset (or None: not a port)
        self.src = open(path).read()
        self.tree = ast.parse(self.src)
        self.assigns = {}       # name -> [expr]
        self.funcs = {}         # name -> FunctionDef (classes map to __init__)
        self.parent = {}
        for node in ast.walk(self.tree):
            for ch in ast.iter_child_nodes(node):
                self.parent[ch] = node
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Tuple) and isinstance(node.value, ast.Tuple) \
                            and len(t.elts) == len(node.value.elts):
                        for te, ve in zip(t.elts, node.value.elts):
                            if isinstance(te, ast.Name):
                                self.assigns.setdefault(te.id, []).append(ve)
                    elif isinstance(t, ast.Name):
                        self.assigns.setdefault(t.id, []).append(node.value)
                    elif isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == 'self':
                        self.assigns.setdefault('self.' + t.attr, []).append(node.value)
            if isinstance(node, ast.FunctionDef):
                self.funcs.setdefault(node.name, node)
            if isinstance(node, ast.ClassDef):
                for b in node.body:
                    if isinstance(b, ast.FunctionDef) and b.name == '__init__':
                        self.funcs[node.name] = b

    def enclosing_func(self, node):
        while node in self.parent:
            node = self.parent[node]
            if isinstance(node, ast.FunctionDef):
                return node
        return None

    def calls_to(self, fname):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if name == fname:
                    yield node

    def resolve(self, e, ctx, depth=0):
        """-> set of int offsets from TEST_PORT_BASE."""
        if depth > 12:
            raise Unresolved(f'{self.path}: resolution too deep at line {getattr(e, "lineno", "?")}')
        if isinstance(e, ast.Constant) and isinstance(e.value, int):
            raise Unresolved(f'{self.path}:{e.lineno}: literal port {e.value} (not from argv)')
        k = self._argv_index(e)
        if k is not None:
            off = self.argmap.get(k)
            if off is None:
                raise Unresolved(f'{self.path}:{e.lineno}: sys.argv[{k}] is a port here, but the recipe '
                                 f'passes no port expression in that position')
            return {off}
        if isinstance(e, ast.BinOp) and isinstance(e.op, (ast.Add, ast.Sub)):
            sign = 1 if isinstance(e.op, ast.Add) else -1
            if isinstance(e.right, ast.Constant) and isinstance(e.right.value, int):
                return {v + sign * e.right.value for v in self.resolve(e.left, ctx, depth + 1)}
            if isinstance(e.left, ast.Constant) and isinstance(e.left.value, int) and sign == 1:
                return {v + e.left.value for v in self.resolve(e.right, ctx, depth + 1)}
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id == 'int' and len(e.args) == 1:
            return self.resolve(e.args[0], ctx, depth + 1)
        name = None
        if isinstance(e, ast.Name):
            name = e.id
        elif isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id == 'self':
            name = 'self.' + e.attr
        if name:
            fn = ctx
            if fn is not None and not name.startswith('self.'):
                params = [a.arg for a in fn.args.args]
                if name in params:
                    return self._param(fn, params.index(name), depth)
            if name in self.assigns:
                out = set()
                for v in self.assigns[name]:
                    out |= self.resolve(v, self.enclosing_func(v), depth + 1)
                return out
        raise Unresolved(f'{self.path}:{getattr(e, "lineno", "?")}: cannot resolve {ast.unparse(e)!r}')

    def _param(self, fn, idx, depth):
        # a class's __init__ is called by the class name
        names = [k for k, v in self.funcs.items() if v is fn and k != fn.name]
        fname = names[0] if names else fn.name
        is_method = fn.args.args and fn.args.args[0].arg == 'self'
        argi = idx - (1 if is_method else 0)
        out, seen = set(), False
        for call in self.calls_to(fname):
            if argi < len(call.args):
                seen = True
                out |= self.resolve(call.args[argi], self.enclosing_func(call), depth + 1)
        if not seen:
            raise Unresolved(f'{self.path}: no call site gives parameter {idx} of {fname}()')
        return out

    @staticmethod
    def _argv_index(e):
        """k for sys.argv[k], int(sys.argv[k]), or `int(sys.argv[k]) if ... else N`; else None."""
        if isinstance(e, ast.IfExp):
            return Script._argv_index(e.body)
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id == 'int' and e.args:
            return Script._argv_index(e.args[0])
        if (isinstance(e, ast.Subscript) and isinstance(e.value, ast.Attribute) and e.value.attr == 'argv'
                and isinstance(e.slice, ast.Constant) and isinstance(e.slice.value, int)):
            return e.slice.value
        return None

    def listens(self):
        """[(offset, form, kind, line)] for every QEMU listen f-string."""
        out = []
        resolved = set()
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.JoinedStr):
                continue
            parts = node.values
            for i, v in enumerate(parts):
                if not isinstance(v, ast.FormattedValue) or i == 0:
                    continue
                pre = parts[i - 1]
                if not (isinstance(pre, ast.Constant) and isinstance(pre.value, str)):
                    continue
                for tail, form in FORMS:
                    if pre.value.endswith(tail):
                        kind = self._kind(node, form)
                        for off in sorted(self.resolve(v.value, self.enclosing_func(node))):
                            out.append((off, form, kind, node.lineno))
                        resolved.add(id(node))
                        break
        # fail closed: a listen address written any other way ('tcp::%d' % p, 'tcp::' + str(p), ...)
        docstrings = {id(b.value) for n in ast.walk(self.tree)
                      if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                      for b in n.body[:1] if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.JoinedStr) and id(node) not in resolved:
                text = ''.join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings \
                    and not isinstance(self.parent.get(node), ast.JoinedStr):
                text = node.value
            else:
                continue
            if re.search(r'tcp:(127\.0\.0\.1)?:|listen=:', text):
                raise Unresolved(f'{self.path}:{node.lineno}: listen address not in a resolvable '
                                 f'f-string: {text[:50]!r}')
        return out

    def _kind(self, node, form):
        if form == 'listen=:P':
            return 'netdev'
        par = self.parent.get(node)
        if isinstance(par, ast.List):
            i = par.elts.index(node)
            if i > 0 and isinstance(par.elts[i - 1], ast.Constant):
                flag = par.elts[i - 1].value
                if flag in ('-serial', '-monitor'):
                    return flag[1:]
        line = self.src.split('\n')[node.lineno - 1]
        prev = self.src.split('\n')[node.lineno - 2] if node.lineno > 1 else ''
        for flag in ('-monitor', '-serial'):
            if flag in line or flag in prev:
                return flag[1:]
        raise Unresolved(f'{self.path}:{node.lineno}: listen address with no -serial/-monitor flag')


# ---------------- inventory ----------------

def entry(off, form, kind, src):
    return {'offset': off, 'form': form, 'kind': kind, 'source': src}


def inventory():
    vars_, recipes = makefile()
    inv, skipped = {}, []
    lists = {k: vars_[k].split() for k in vars_ if k.endswith('_ALL')}
    for name, body in sorted(recipes.items()):
        rvars = recipe_vars(body)
        loop_all = None
        for _, ln in body:
            m = re.search(r'for a in \$\((\w+_ALL)\)', ln) or re.search(r'for spec in \$\((\w+_ALL)\)', ln)
            if m:
                loop_all = m.group(1)
        fixtures = {}
        if loop_all:
            for i, item in enumerate(lists[loop_all]):
                fx, off = (item.split(':') + [None])[:2]
                fixtures[fx] = {'INDEX': i, 'OFF': int(off) if off else None}
        else:
            fixtures[None] = {}
        out = {}
        for fx, fv in fixtures.items():
            ents = []
            def mko(e, n):
                o = mk_offset(e, rvars)
                if isinstance(o, tuple):
                    o = o[1] + fv['INDEX'] if o[0] == 'INDEX' else fv['OFF']
                return o
            for n, ln in body:
                if fx == 'test_metacompiler' or fx is None or loop_all != 'META_FIXTURES_ALL':
                    for m in re.finditer(r'-(serial|monitor)\s+tcp:(127\.0\.0\.1)?:([^,\s]+)', ln):
                        form = 'tcp:127.0.0.1:P' if m.group(2) else 'tcp::P'
                        ents.append(entry(mko(m.group(3), n), form, m.group(1), f'Makefile:{n}'))
                    for m in re.finditer(r'-netdev\s+\S*listen=:([^,\s]+)', ln):
                        ents.append(entry(mko(m.group(1), n), 'listen=:P', 'netdev', f'Makefile:{n}'))
                for m in re.finditer(r'python3 tests/(\$\$\w+|\w+)\.py([^;]*)', ln):
                    script = m.group(1)
                    if script.startswith('$$'):
                        script = fx
                    argmap = {}
                    for k, arg in enumerate(m.group(2).split(), 1):
                        try:
                            argmap[k] = mko(arg, n)
                        except Unresolved:
                            argmap[k] = None      # not a port (an image path, a mode word, ...)
                    path = os.path.join(ROOT, 'tests', script + '.py')
                    if not os.path.exists(path):
                        skipped.append(f'{name}{"/" + fx if fx else ""}: tests/{script}.py absent')
                        ents.append({'script': f'tests/{script}.py', 'absent': True})
                        continue
                    for off, form, kind, line in Script(path, argmap).listens():
                        ents.append(entry(off, form, kind, f'tests/{script}.py:{line}'))
            # one row per (offset, form, kind); a port opened at two sites is still one port
            seen, uniq = set(), []
            for e in ents:
                key = (e.get('offset'), e.get('form'), e.get('kind'), e.get('script'))
                if key not in seen:
                    seen.add(key)
                    uniq.append(e)
            if uniq:
                out[fx or '-'] = sorted([e for e in uniq if 'absent' not in e], key=lambda e: (e['offset'], e['kind'])) \
                    + [e for e in uniq if 'absent' in e]
        if out:
            inv[name] = out
    return inv, skipped


def strip_sources(inv):
    """The comparison ignores source line numbers (they move with edits)."""
    return {r: {f: [{k: v for k, v in e.items() if k != 'source'} for e in ents] for f, ents in fx.items()}
            for r, fx in inv.items()}


def main():
    try:
        inv, skipped = inventory()
    except Unresolved as e:
        print(f'port_inventory: UNRESOLVED: {e}', file=sys.stderr)
        sys.exit(2)
    if '--check' not in sys.argv:
        print(json.dumps(inv, indent=1, sort_keys=True))
        for s in skipped:
            print(f'SKIPPED: {s}', file=sys.stderr)
        return
    committed = json.load(open(sys.argv[sys.argv.index('--check') + 1]))
    bad = 0
    for s in skipped:
        print(f'SKIPPED: {s} (its committed entries are not compared)')
    absent = {s.split(': ')[0] for s in skipped}
    for r in sorted(set(inv) | set(committed)):
        for fx in sorted(set(inv.get(r, {})) | set(committed.get(r, {}))):
            key = f'{r}{"/" + fx if fx != "-" else ""}'
            if key in absent:
                continue
            a = strip_sources({r: {fx: inv.get(r, {}).get(fx, [])}})
            b = strip_sources({r: {fx: committed.get(r, {}).get(fx, [])}})
            if a != b:
                print(f'DRIFT: {key}: generated {a[r][fx]} != committed {b[r][fx]}')
                bad += 1
    for r, fx in inv.items():
        for f, ents in fx.items():
            for e in ents:
                if e.get('form') == 'tcp::P' and e.get('kind') in ('serial', 'monitor'):
                    print(f'TCP-ANY: {r}/{f}: {e["kind"]} +{e["offset"]} listens on every interface (tcp::P) at {e["source"]}')
                    bad += 1
    _, recipes = makefile()
    for r, fx in inv.items():
        body = '\n'.join(ln for _, ln in recipes.get(r, []))
        loop = any(f != '-' for f in fx)
        if not re.search(r'\$\(PORTS_FREE\) --recipe ' + re.escape(r) + (r' --fixture ' if loop else r' --base'), body):
            print(f'UNGUARDED: {r} starts QEMU but does not run $(PORTS_FREE) --recipe {r}'
                  + (' --fixture <fixture>' if loop else ''))
            bad += 1
    n = sum(len([e for e in ents if 'offset' in e]) for fx in inv.values() for ents in fx.values())
    print(f'port inventory: {len(inv)} recipes, {n} listen entries; {bad} problem(s)')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
