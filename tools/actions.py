"""actions.py : each monster's AI actions, for the next-action test aid (module/nextact.c, tools/nextact.py).

The pairs a monster's AI can pick are the native `00 cat num` entries of its EMC table (cmd_tbl; tools/emc.py refs, a
heuristic tokenizer): the module swaps the pick where GU's selector starts one of them (nextact.c), so the list is in
GU's numbering, the one the class dispatches (a port that renumbers 4U's actions lists its own numbers, e.g. Monoblos'
(c, 208 + n)). Table of a monster: its arc's own enemy\\cmd_tbl\\emNNN_VV_cmdtbl, else the shared one it ships (GU
variants, Shah Dalamadur's), never a 4U source copy (*_4u).
Names: a port keeps monsters/<package>/actions.toml (every entry of the package; `check` refuses a port whose table picks
a pair the file lacks, so a port's AI change updates it); GU's own monsters may get names in
data/gu_actions/emNNN_VV.toml, same format, optional. A file:
    [[monster]]
    em = 0x60d                       # EN_ID: variant << 8 | em number
    entry = "g_crimson_fatalis"      # allocations.toml entry (ports)
    actions = [
      { cat = 7, num = 74, name = "Heatwave (ahead)", needs = "" },   # needs: the state it wants (flying, rider ...)
    ]

  actions.py list 0x60d       the pairs of that monster ID (port or GU), with names
  actions.py init PACKAGE     write / extend monsters/PACKAGE/actions.toml with every pair of its entries (names kept)
  actions.py check            every port's actions.toml covers its AI table (module/build.py runs it)
"""
import os, sys, tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import alloc, emc, paths   # noqa: E402
sys.path.insert(0, paths.GU_PY)
import arcpack   # noqa: E402

T_EMC = 0x3AABBA02
GU_NAMES = os.path.join(ROOT, 'data', 'gu_actions')


def arc_name(em):
    return 'em%03d_%02d' % (em & 0xff, em >> 8)


def entry_of(em):
    for m in alloc.monsters():
        if m['em_id'] == em: return m
    return None


def table(em):
    """the AI table (EMC bytes) of monster ID em: the port's arc, else GU's"""
    name = arc_name(em)
    m = entry_of(em)
    if m:
        path = os.path.join(paths.monster(alloc.package(m)), 'romfs', 'nativeNX', 'arc', 'enemy', name + '.arc')
        data = open(path, 'rb').read()
    else:
        from romfs import RomFS
        data = RomFS(paths.GU_ROMFS).read('/nativeNX/arc/enemy/%s.arc' % name)
    tabs = {p: d for p, t, d in arcpack.read(data)[1] if t == T_EMC and not p.endswith('_4u')}
    own = 'enemy\\cmd_tbl\\%s_cmdtbl' % name
    assert tabs, 'no AI table in %s.arc' % name
    return tabs.get(own) or tabs[sorted(tabs)[0]]


def pairs(em):
    """the native (cat, num) pairs its AI table names, sorted"""
    _, groups = emc.parse(table(em))
    return sorted({p for g in groups for s in g for p in emc.refs(s)[0]})


def names_file(em):
    m = entry_of(em)
    if m: return os.path.join(paths.monster(alloc.package(m)), 'actions.toml')
    return os.path.join(GU_NAMES, arc_name(em) + '.toml')


def load(path):
    """{em: {(cat, num): action dict}} of an actions file ({} when it does not exist)"""
    if not os.path.exists(path): return {}
    with open(path, 'rb') as f:
        doc = tomllib.load(f)
    return {m['em']: {(a['cat'], a['num']): a for a in m.get('actions', [])} for m in doc.get('monster', [])}


def names(em):
    return load(names_file(em)).get(em, {})


def toml_str(s):
    return '"%s"' % s.replace('\\', '\\\\').replace('"', '\\"')


def write(path, title, mons):
    """mons: [(em, entry or None, {(cat, num): action})]"""
    out = ['# %s: the AI\'s native actions (GU numbering, the pairs its cmd_tbl picks) for tools/nextact.py.' % title,
           '# Kept with the port: tools/actions.py check refuses a missing pair; `init` adds new ones.', '']
    for em, entry, acts in mons:
        out += ['[[monster]]', 'em = 0x%x' % em] + (['entry = %s' % toml_str(entry)] if entry else []) + ['actions = [']
        for (c, n), a in sorted(acts.items()):
            out.append('  { cat = %d, num = %d, name = %s, needs = %s },' % (c, n, toml_str(a.get('name', '')),
                                                                         toml_str(a.get('needs', ''))))
        out += [']', '']
    open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(out))


def init(package):
    ents = [m for m in alloc.monsters() if alloc.package(m) == package]
    assert ents, 'no allocations.toml entry in package %r' % package
    path = os.path.join(paths.monster(package), 'actions.toml')
    old = load(path)
    mons = []
    for m in ents:
        acts = dict(old.get(m['em_id'], {}))
        for p in pairs(m['em_id']):
            acts.setdefault(p, dict(cat=p[0], num=p[1], name='', needs=''))
        mons.append((m['em_id'], m['name'], acts))
    write(path, paths.package_toml(package).get('title', package), mons)
    print('wrote %s: %s' % (path, ', '.join('%s %d' % (e, len(a)) for _, e, a in mons)))


def check():
    """problems: a port without actions.toml, or one whose AI table picks a pair it lacks"""
    bad = []
    for m in alloc.monsters():
        em, path = m['em_id'], names_file(m['em_id'])
        if not os.path.exists(path):
            bad.append('%s: no %s (tools/actions.py init %s)' % (m['name'], os.path.relpath(path, ROOT),
                                                                 alloc.package(m)))
            continue
        miss = [p for p in pairs(em) if p not in names(em)]
        if miss:
            bad.append('%s: %s lacks %s (tools/actions.py init %s)' % (m['name'], os.path.relpath(path, ROOT),
                       ' '.join('%d/%d' % p for p in miss), alloc.package(m)))
    return bad


def main(argv):
    if argv[:1] == ['list'] and len(argv) == 2:
        em = int(argv[1], 0)
        nm = names(em)
        for p in sorted(set(pairs(em)) | set(nm)):
            a = nm.get(p, {})
            print('%2d/%-3d %s%s' % (p[0], p[1], a.get('name', ''), ('  [needs: %s]' % a['needs']) if a.get('needs') else ''))
    elif argv[:1] == ['init'] and len(argv) == 2:
        init(argv[1])
    elif argv == ['check']:
        bad = check()
        for b in bad: print(b)
        print('actions: %s' % ('%d problem(s)' % len(bad) if bad else 'every port\'s list covers its AI table'))
        return 1 if bad else 0
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
