"""build_em013_06_arc.py : build nativeNX/arc/enemy/em013_06.arc (G-rank Crimson Fatalis = 4U em117 = GU Fatalis
variant 6, ID 0x60d) + its data file section FILE.

  build_em013_06_arc.py      build, verify, then write (paths in monsters/g_crimson_fatalis/):
      romfs/nativeNX/arc/enemy/em013_06.arc
      tools/em013_06_manifest.json         (51 manifest fields, file IDs, sources)
      gen/FILE.sec                         (data file section FILE: manifest + file table, tools/portdata.py)

Layout = GU's own variant arcs (em005_01, em057_01 of the earlier ports): the variant's own files under
enemy\\em013\\em013_06\\..., the files it shares with GU's Crimson Fatalis (em013_01) under em013_01's paths and file
IDs. GU's class uEm013_00 runs it (variant byte 6, notes/plan.md 1). 4U runs em117 on Fatalis' class with em077's
motions, camera and AI and em078's (Crimson's) effect files; every file em117.arc shares with em078.arc is
byte-identical, and em117's attackdata / hitsize / bodydata equal em078's (C, asserted in shared_4u). GU's em013_01 is
Capcom's conversion of em078, so everything but em117's own files stays GU's Crimson:
  own, converted from MH4U em117.arc:
      mod\\em013_06 MOD + MRL + textures   tools/mod4u2gu.py; MRL on GU templates (tools/mrl_build.py) with 4U's material
                                           animations, among them the rage glow "Angry_Start" / "Angry_End" that GU's
                                           slot 132 plays for variant 6 (notes/plan.md 2)
      mod\\em013_06 XFS                    GU em013_01's parts states (em117's mesh groups = GU's, asserted)
      sound call / waves / bank / request  tools/snd4u2gu.py monster_entries (4U call em117 + bank snd_em117)
      effect\\pel\\em\\em013_06u, PSLs      GU em013_01u + em117_1's 7 records; GU's PSLs with the foot dust out and
                                           em117_1's slots in at 4U's frames (effects(); the maintainer's rule of
                                           2026-11-22: GU's look for the shared moves, em117's own records on top)
      dt_tune\\em013_06_dttune             GU em013_01's + the bytes where tools/dt_convert.py gives em117 != em078
      cmd_tbl\\em013_06_cmdtbl             GU em013_00's table with 4U's g0 s10, g1 s113 s118 s119 put back (cmdtbl())
      hagi\\hagi_s0..s4_em013_06           carves: 4U G table in s4, GU's filler in s0..s3 (tools/hagi_em013_06.py)
      shell\\em\\em013_06_shell01\\...      shell family of its new shells: GU em013_01_shell01 renamed, HDS / HTS from
                                           the 4U records (shell_family(); no manifest field, extra file ID)
      sound\\bgm\\battle\\bgm_em013_06      its own battle STQR (tools/bgm_em013_06.py; extra file ID)
  shared, GU em013_01 (original paths + file IDs): motions, camera, PTS, PEL c, the shell families GU's class posts
      for its Crimson (slot 86 preloads them; module code gives variant 6 variant 1's), attack / hit / body / cambody
      data, dtbase (= the em078 and em117 conversions), dtbparts, area data (Ingle Isle, GU stage 19, is Crimson's).
Known deviation: 4U emd word 32 (em117's own part colours; em078 / em117 differ there) has no known GU field, as Black
Gravios'.
Inputs besides the arcs: dump/converted/em117/dt_em078/ and dt_em117/ (build.py step dt: tools/dt_convert.py, donor
em013_01), dump/converted/g_crimson_fatalis/bgm_em013_06.stqr (step bgm), the 4U ROM (Ingle Isle area colour).
"""
import json, os, re, struct, sys, zlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MON = os.path.dirname(HERE)                         # monsters/g_crimson_fatalis
ROOT = os.path.dirname(os.path.dirname(MON))
sys.path.insert(0, os.path.join(ROOT, 'tools'))     # core converters + paths.py
import paths
sys.path.insert(0, paths.GU_PY)
from romfs import RomFS
import alloc, arcpack, ctr, efl4u2gu, emc, emdata4u, mod as modlib, mod4u2gu, mrl, mrl_anim, mrl_build, portdata, \
    snd4u2gu, tex
# the earlier ports' helpers this one reuses as they are: Black Gravios' PSL entry writer and Stygian Zinogre's 4U
# shell record rules (the em089 rule, checked on GU's own families there)
sys.path.insert(0, os.path.join(ROOT, 'monsters', 'black_gravios', 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'monsters', 'stygian_zinogre', 'tools'))
from build_em005_01_arc import psl_put, pel_ids
from build_em057_01_arc import hds_rule, hts_rule, rec_4u, vol_4u, efl_4u, gu_world_tail, LIGHT_TEMPLATE

NAME = 'g_crimson_fatalis'
ALLOC = alloc.monster(NAME)
FILE_ID_BASE, FILE_ID_LAST = ALLOC['file_ids']      # IDs served by the module (allocations.toml)
SRC_4U = os.path.join(ROOT, 'dump/romfs/data/em117.arc')
SRC_4U_CRIMSON = os.path.join(ROOT, 'dump/romfs/data/em078.arc')
GU_ARC = '/nativeNX/arc/enemy/em013_01.arc'
OUT_ARC = os.path.join(MON, 'romfs/nativeNX/arc/enemy/em013_06.arc')
OUT_JSON = os.path.join(HERE, 'em013_06_manifest.json')
FILES_TABLE = 0x1732A68          # registry index -> manifest (51 x s32 file IDs)
FILEID_TABLE = 0x15A0CE0         # file ID -> (path hash, type hash), 8 B, entry = ID
T = dict(MOD=0x58A15856, MRL=0x2749C8A8, TEX=0x241F5DEB, XFS=0x7CD0E77E, EMC=0x3AABBA02)
P4 = 'enemy\\em117\\'            # 4U em117's own paths
P77 = 'enemy\\em077\\'           # 4U Fatalis' files em117.arc ships (motions, camera, AI)
P1 = 'enemy\\em013\\em013_01\\'  # GU variant 1 (Crimson)
P = 'enemy\\em013\\em013_06\\'   # ours
# manifest fields with our own file: IDs are given in this order (append only: IDs never move once shipped)
OWN_ORDER = [0, 3, 12, 13, 17, 18, 19, 20, 21, 33, 37, 46, 47, 48, 49, 50]
EXTRA_ORDER = ['bgm_stqr', 'shell01']   # own files without a manifest field, IDs after the fields' (append only)
DT_DIR = os.path.join(ROOT, 'dump/converted/em117')           # build.py step dt
BGM_STQR = 'sound\\bgm\\battle\\bgm_em013_06'                 # tools/bgm_em013_06.py
BGM_STQR_SRC = os.path.join(ROOT, 'dump/converted/g_crimson_fatalis/bgm_em013_06.stqr')
T_STQR = 0x167DBBFF
# Material type (MRL w6 bits 21-28) = the 'mNN' of the 4U name; GU em013_01's materials carry em117's names for the
# five it has (C), with the same numbers. 4U's three additive layers (m51 / m52, the rage glow) have no GU twin.
mrl_build.TEMPLATES.setdefault('light', LIGHT_TEMPLATE)    # Stygian's preset for 4U IAFilter2 additive filters
assert mrl_build.TEMPLATES['light'] == LIGHT_TEMPLATE


def phash(path):
    return zlib.crc32(path.encode('ascii')) ^ 0xFFFFFFFF


def manifest_of(img, index):
    return list(struct.unpack_from('<51i', img, struct.unpack_from('<I', img, FILES_TABLE + 4 * index)[0]))


def fileid_entry(img, fid):
    return struct.unpack_from('<II', img, FILEID_TABLE + 8 * fid)


def shared_4u(S, notes):
    """assert what lets every non-own file stay GU Crimson's: em117.arc's em077 / em078 files equal em078.arc's, and
    the 4U attack / hit / body data of em078 and em117 are equal"""
    _, s78 = arcpack.read(open(SRC_4U_CRIMSON, 'rb').read())
    g78 = {(p, t): d for p, t, d in s78}
    shared = [(k, d) for k, d in S.items() if k in g78]
    assert shared and all(g78[k] == d for k, d in shared), 'em117.arc no longer ships em078.arc\'s files'
    d78, d117 = emdata4u.load_4u('em078'), emdata4u.load_4u('em117')
    for name, conv in (('attackdata', lambda d: emdata4u.attackdata(d['etd'])),
                       ('hitsize', lambda d: emdata4u.hitsize(d['etd'])),
                       ('bodydata', lambda d: emdata4u.bodydata(d['emd'], 8))):
        assert conv(d78) == conv(d117), name + ' of em078 and em117 differ: convert it too'
    notes.append('4U em117.arc: %d files = em078.arc\'s (motions, camera, AI, shared effects); attackdata / hitsize / '
                 'bodydata = em078\'s' % len(shared))


def textures(S, r4, slots, out, gu_tex, spec_type):
    """GU texture paths of one 4U material's albedo / normal maps, converted on first use into `out` (Stygian
    Zinogre's rule, build_em057_01_arc.textures): albedo -> BC3 + its '+A' specular map (the BM alpha for 4U
    specular mask type 1, the NM_MIRROR's alpha for type 2), normal map -> BC5. em117's NM_MIRRORs (type 2: leg,
    body, wing) are half the albedo's height, not Stygian's double width: they cover the albedo's whole UV range at
    half the vertical resolution (S: the wing's NM alpha correlates 0.43 with its albedo squashed 2x vertically, against
    0.09 / 0.13 for either half, no flip better; GU's own Crimson textures are Capcom's HD repaint, no help), so the
    GU normal map stays as it is and the mask is its alpha with every row doubled, at the albedo's size."""
    paths_of = {}
    nm = slots.get('tNormalMap') if spec_type == 2 else None
    nm_src = r4['textures'][nm - 1][1] if nm else None
    for slot, v in slots.items():
        if not v: continue
        src = r4['textures'][v - 1][1]
        name = src.split('\\')[-1]
        if src not in gu_tex:
            t = tex.decode(S[(src, T['TEX'])])
            path = P + 'mod\\em013_06_' + name.split('em117_')[-1]
            if slot == 'tAlbedoMap':
                m = t[..., 3]
                if nm_src:
                    n = tex.decode(S[(nm_src, T['TEX'])])
                    assert 2 * n.shape[0] == t.shape[0] and n.shape[1] == t.shape[1], (src, nm_src, n.shape, t.shape)
                    m = np.repeat(n[..., 3], 2, axis=0)
                s = np.empty_like(t); s[..., 0] = s[..., 1] = s[..., 2] = m; s[..., 3] = 255
                out += [(path, T['TEX'], tex.encode_gu(t, 'bc3')), (path + '+A', T['TEX'], tex.encode_gu(s, 'bc3'))]
                gu_tex[('spec', src)] = nm_src
            else:
                out.append((path, T['TEX'], tex.encode_gu(t, 'bc5')))
            gu_tex[src] = path
        elif slot == 'tAlbedoMap' and spec_type:
            assert gu_tex[('spec', src)] == nm_src, 'materials sharing %s want other specular masks' % src
        paths_of[slot] = gu_tex[src]
        if slot == 'tAlbedoMap':
            paths_of['tSpecularMap'] = gu_tex[src] + '+A'
    return paths_of


def model(S, rom, notes):
    """em117's MOD + MRL + textures -> [(path, type, data)], the parsed 4U MOD. Templates by Stygian Zinogre's rules
    (build_em057_01_arc.model): additive -> 'add', IAFilter2 additive filters -> 'light', normal-mapped -> 'solid_nm',
    alpha-tested -> 'solid_at' / 'tar', else 'solid'; every 4U material animation converted with the 4U material's
    own constants for the variables its tracks drive (the rage glow "Angry_Start" / "Angry_End", 2 per material on
    all but the eye). MRL before MOD, as in GU's arcs."""
    d4, d4m = S[(P4 + 'mod\\em117', T['MOD'])], S[(P4 + 'mod\\em117', T['MRL'])]
    m4, r4 = modlib.parse(d4), mrl.read(d4m)
    anims4 = mrl_anim.material_anims(d4m)[1]
    out, tex_paths, tex_index, mats, gu_tex = [], [], {}, [], {}
    for mname in m4['material_names']:
        mm = [x for x in r4['mats'] if x['name'] == mrl_build.name_hash(mname)]
        assert len(mm) == 1, mname
        mm = mm[0]
        states = [s for s in mm['states'] if s]
        std = [v for n, t, v in mm['params'] if t == 1 and n == 'CBMaterialStd']
        spec_at = mrl.cb_layout(0x20, 'CBMaterialStd')['iMaterialStdSpecularMaskType'][0]
        spec_type = struct.unpack_from('<I', mm['block'], std[0] + 4 * spec_at)[0] if std else 1
        assert spec_type in (0, 1, 2), (mname, spec_type)
        gp = textures(S, r4, {n: v for n, _, v in mm['params'] if n in ('tAlbedoMap', 'tNormalMap')}, out, gu_tex,
                      spec_type)
        slots = {}
        for slot, path in gp.items():
            if path not in tex_index:
                tex_paths.append(path); tex_index[path] = len(tex_paths)
            slots[slot] = tex_index[path]
        stdf = struct.unpack_from('<8f', mm['block'], 0x60)       # emission rgba, diffuse rgba
        emissive = max(stdf[0:3]) > 0 and max(stdf[4:7]) == 0
        key = 'blend' if 'BSBlendAlpha' in states else 'add' if 'BSAddAlpha' in states else \
              ('solid_nm' if 'tNormalMap' in slots else 'unlit' if emissive else 'solid')
        if 'IAFilter2' in states:
            key = 'light'
        alpha_test = 'BSSolid' in states and mm['words'][7] & mrl_build.W7_ALPHATEST
        if alpha_test:
            key = 'solid_at' if 'tNormalMap' not in slots else 'tar'
        w7 = mm['words'][7]
        extra = dict(mtype=int(re.search(r'_m(\d\d)_', mname).group(1)), bias=(w7 >> 16) & 0xF)
        if alpha_test:
            extra['alpha_ref'] = (w7 >> 8) & 0xFF
        consts = {}
        ents4 = anims4.get(mm['name'], [])
        if ents4:
            std_off = [v for n, t, v in mm['params'] if t == 1 and n == 'CBMaterialStd']
            anim_vars = mrl_anim.animated_targets(ents4)
            if std_off:
                consts.update({k: v for k, v in mrl_anim.static_constants(mm['block'][std_off[0]:], 1.0).items()
                               if k in anim_vars})
            ge = mrl_anim.gu_entries(ents4, mrl_build.cb_words(rom, key))
            for g, e in zip(ge, ents4):
                g['flags'] |= e['flags'] & mrl_anim.FLAG_AUTOPLAY
            extra['anim'] = mrl_anim.build(ge)
        own_states = [s for s in states if s.startswith('RS')]
        cst = [v for n, t, v in mm['params'] if t == 1 and n == 'CBMaterialConstant']
        if key == 'light' and cst:
            fo = mrl.cb_layout(0x20, 'CBMaterialConstant')['fMaterialConstantBase'][0]
            consts[('$Globals', 'fConstantColor')] = struct.unpack_from('<4f', mm['block'], cst[0] + 4 * fo)
        mats.append((mname, key, slots, own_states, consts, extra))
        notes.append('material %s: template %s, type %d, %s, 4U specular mask type %d%s' % (
            mname, key, extra['mtype'], sorted(p.split('\\')[-1] for p in gp.values()), spec_type,
            ', 4U animations %s' % [e['name'] for e in ents4] if ents4 else ''))
    mod_bytes = mod4u2gu.convert(d4)
    mrl_bytes = mrl_build.build(rom, mats, tex_paths)
    assert [m[0] for m in mats] == modlib.parse(mod_bytes)['material_names'], 'MOD / MRL material lists differ'
    out += [(P + 'mod\\em013_06', T['MRL'], mrl_bytes), (P + 'mod\\em013_06', T['MOD'], mod_bytes)]
    return out, m4


def parts_xfs(gu_xfs, gu_mod, groups, notes):
    """GU em013_01's parts states (rMonsterPartsManager XFS) as they are: em117's mesh groups are GU's model's (4U em117's
    visibility rows are em078's: their emd files differ only in word 32, C)"""
    r, states = emdata4u.parse_xfs_states(gu_xfs)
    data, _ = emdata4u.xfs_states(states)
    assert data == gu_xfs[r:], 'XFS round trip differs: emdata4u.xfs_states no longer matches GU files'
    gu_groups = sorted({x['group'] for x in modlib.parse(gu_mod)['mesh_list']})
    assert groups == gu_groups, ('em117 mesh groups differ from GU em013_01\'s', groups, gu_groups)
    notes.append('parts states: GU em013_01\'s %d (mesh groups %s = GU\'s)' % (len(states), groups))
    return gu_xfs


def dttune(gu, notes):
    """GU em013_01's dttune + the bytes where tools/dt_convert.py (donor em013_01) gives em117 != em078 (the HP base
    word, 4U etd word 4: 8000 -> 8500, C); GU's retuned bytes and these never overlap (asserted)"""
    c78 = open(os.path.join(DT_DIR, 'dt_em078', 'dttune.bin'), 'rb').read()
    c117 = open(os.path.join(DT_DIR, 'dt_em117', 'dttune.bin'), 'rb').read()
    assert len(c78) == len(c117) == len(gu)
    delta = [i for i in range(len(gu)) if c78[i] != c117[i]]
    retuned = {i for i in range(len(gu)) if c78[i] != gu[i]}
    assert delta and not retuned & set(delta), 'GU retuned bytes em117 changes: %s' % sorted(retuned & set(delta))
    out = bytearray(gu)
    for i in delta: out[i] = c117[i]
    notes.append('dttune: GU em013_01 + %d bytes of 4U em078 -> em117 differences at %s (GU retuned %d other bytes)'
                 % (len(delta), [hex(i) for i in delta], len(retuned)))
    return bytes(out)


def dtbase_check(gu, notes):
    """GU em013_01's dtbase stays: it equals both conversions (asserted)"""
    for em in ('em078', 'em117'):
        c = open(os.path.join(DT_DIR, 'dt_' + em, 'dtbase.bin'), 'rb').read()
        assert c == gu, 'GU em013_01 dtbase != the %s conversion: make it an own file' % em
    notes.append('dtbase: GU em013_01\'s (= the em078 and em117 conversions)')


# AI table (notes/plan.md 3, C). 4U em077_cmd (all four arcs ship it) switches on the species in g0 s3 (op 0x46): em 117
# -> selector 10. GU's em013_00_cmdtbl (all three variants) does the same on the variant (op 0x92): 6 -> 10, but GU put
# its stub (`a6 ff`) in place of 4U's g0 s10 and of g1 s113 s118 s119 (the heatwave scripts it calls), among others
# no script or code reaches. So our table = GU's with those four put back; every other script they call is the same in
# both tables (asserted), they hold no 4U-only op (no species switch, area move or stage case) and their native
# actions are GU's handlers (7/74..76 take module code: GU sends them to its no-case thunk).
EMC_PUT_BACK = [(0, 10), (1, 113), (1, 118), (1, 119)]
EMC_4U_ONLY_OPS = {0x03, 0x06, 0x36, 0x4d, 0x2a, 0x46}     # 4U area ops, stage switches, species switch
EMC_STUB = b'\xa6\xff'


def cmdtbl(d4, gu, img, notes):
    lens = img[emc.LEN_TABLE:emc.LEN_TABLE + emc.LEN_COUNT]
    ver, u4 = emc.parse(d4)
    gver, g = emc.parse(gu)
    out = [list(x) for x in g]
    natives = []
    for gi, k in EMC_PUT_BACK:
        assert g[gi][k] == EMC_STUB, ('GU no longer stubs', gi, k)
        s = u4[gi][k]
        toks = emc.tokens(s, lens)
        assert not {t[0] for t in toks} & EMC_4U_ONLY_OPS, ('4U-only op', gi, k)
        for t in toks:
            if t[0] == 0x14:
                c = t[1]
                assert (1, c) in EMC_PUT_BACK or u4[1][c] == g[1][c], ('calls a script GU changed', gi, k, c)
            if t[0] == 0x00:
                natives.append('%d/%d' % (t[1], t[2]))
        out[gi][k] = s
    notes.append('AI table: GU em013_00 + 4U %s (native actions %s)' % (
        ['g%d s%d' % a for a in EMC_PUT_BACK], sorted(set(natives))))
    return emc.build(out, gver)


def ingle_soil(notes):
    """RGBA area colour for the effects: the 4U Ingle Isle's (stage 9, m09a01: both em117 quests) area_color_soil (the
    Battlequarters' m19a03d-col layout, colour at +0xd0), as Stygian's arena_soil. GU has no area tint."""
    m19 = os.path.join(ROOT, 'dump/m19_unpacked/m19a03/stage/m19d/m19a03d/sdl/m19a03d-col.4c0db839')
    ref = open(m19, 'rb').read()
    n, _ = ctr.main_ncch(efl4u2gu.ROM_4U)
    _, ents = arcpack.read(n.romfs_reader().read('/loc/data/m09a01.arc'))
    d = [d for p, t, d in ents if p == 'stage\\m09d\\m09a01d\\sdl\\m09a01d-col'][0]
    assert len(d) == len(ref) and re.findall(rb'[ -~]{4,}', d) == re.findall(rb'[ -~]{4,}', ref), 'm09a01d-col layout'
    soil = bytes(round(255 * x) for x in struct.unpack_from('<4f', d, 0xd0))
    notes.append('effect area colour: 4U Ingle Isle m09a01 soil %s' % (tuple(soil),))
    return soil


# Effects (the maintainer's choice of 2026-11-22: GU's own look for every move em117 shares with GU's Crimson, em117's
# own 4U records on top). GU's Crimson PSLs (em013_00's, every variant's) name GU's PEL c / u records; ours are copies:
#   - GU's foot dust (PEL c list 1 ids 0..3 = cm202_020 on joints 90 / 80 / 50 / 40, PSL kind 3) out where it stands
#     for 4U's gated dust: 4U posts em077_0 records 38..47 (MEF b0 3) under condition bit 3, which its footstep loop
#     0x89d600 sets for any new footstep slot of em 77 / 78 / 79 and never for em 117 (C). A GU dust slot goes when the
#     motion's 4U records on that foot are all b0 3; it stays where 4U has an ungated one there (records 10..26, b0 0:
#     em117 shows those in 4U too) or none (GU's own addition: GU's look) (S: GU's slot = 4U's record by the joint);
#   - em117_1's records in at 4U's frames, in every motion whose 4U events name them (FOOT_IDS, CAST_IDS): the
#     stepfire 2000..2003 (b0 4: the same loop sets bit 4 for em 117 at the rising edge of exactly these slots, so
#     the slot's own edge is the condition, no gate) and the heatwave cast 2004..2006 (bank 2 motions 60..62 = 0x23c
#     ..0x23e, b0 0). They go on free PSL slots (4U's slot number when free).
# PEL u = GU em013_01u (list 1: 14 records, ids 100..501) + em117_1's 7 (list 1) + CODE_FX (list 2, after GU's 18).
PEL_U = 'effect\\pel\\em\\em013_06u'
PEL_GU = 'effect\\pel\\em\\em013_01u'
PSL = 'effect\\psl\\enemy\\em013\\em013_06\\mot\\em013_06_%d'
MEF_OWN = 'effect\\mef\\em\\em117_1'
BANKS = (0, 1, 2, 3)            # motion lists: manifest fields 4 + bank (GU's motions), PSL fields 18 + bank (ours)
KIND_PEL_C, KIND_PEL_U = 3, 4
DUST_IDS = {0: 90, 1: 80, 2: 50, 3: 40}            # GU PEL c id -> joint (C, em013_00c)
FOOT_IDS = {2000: 40, 2001: 50, 2002: 90, 2003: 80}   # em117_1 stepfire record -> joint (C)
CAST_IDS = (2004, 2005, 2006)
# code-posted effects of the new shells (efl4u2gu effect_set extra2: list 2 after GU's records), from the 4U shell
# code (C; module em013_06_shell*.c posts them by id): (id, 4U group, element, k, follow, 4U post)
CODE_FX_IDS = range(4100, 4200)
CODE_FX = [
    (4100, 87, 22, -1, False, 'uShell018 6 init 0xc72504: 0xc0a2f8 (87, 22) + 0xc08060 (mask -1), placed at the shell '
                              'with its angles (frame 0xc7277c): the prominence marker'),
    (4101, 87, 19, 0, False, 'uShell037 8 init 0xc836a8: 0xc08628 at (x, y + 50, z), yaw, flags 0x83, mask 1'),
    (4102, 87, 19, 1, False, 'uShell037 8 frame 0xc84300: 0xc08628 at the ground hit, flags 0x20, mask 2 (the scorch)'),
    (4103, 87, 21, 0, True, 'uShell012 51 / 66 flight 0x1027488: on the shell, mask 1'),
    (4104, 87, 21, 1, True, 'uShell012 54 / 55 / 67 / 68 flight 0x1027488: on the shell, mask 2'),
]
CODE_4U = os.path.join(ROOT, 'dump/exefs_v11/mem.bin')       # MH4U v1.1 code, flat from 0x100000


def psl_entry(out, i):
    """(frames, mask, ids, kinds, per-frame bits) of PSL entry i, or None"""
    o = struct.unpack_from('<I', out, 8 + 4 * i)[0]
    if not o:
        return None
    frames, _, _, _, da, _ = struct.unpack_from('<IHBBII', out, o)
    mask = struct.unpack_from('<I', out, da)[0]
    ids = list(struct.unpack_from('<32H', out, da + 4))
    kinds = list(struct.unpack_from('<32I', out, da + 68))
    assert not any(struct.unpack_from('<32I', out, da + 196)), ('PSL entry rest', i)
    nr, ra = struct.unpack_from('<II', out, da + 0x144)
    per = [b for k in range(nr) for b, f in [struct.unpack_from('<II', out, ra + 8 * k)] for _ in range(f)]
    assert len(per) == frames - 1, ('PSL runs', i)
    return frames, mask, ids, kinds, per


def psl_own(gu, lmt4, lmt_gu, known, foot4, bank, log):
    """GU's PSL bank -> ours: the gated foot dust out, em117_1's slots in (see above); foot4 = {em077_0 record id:
    (b0, joint)} of its foot-joint records. -> bytes"""
    out = bytearray(gu)
    assert out[:4] == b'PSL\0' and struct.unpack_from('<H', out, 4)[0] == 2
    n = struct.unpack_from('<H', out, 6)[0]
    ev4 = {e[0]: e for e in efl4u2gu.lmt_events(lmt4) if e}
    evg = efl4u2gu.lmt_events(lmt_gu)

    def gated(i, d):
        """GU dust id d in motion i stands for 4U's bit-3 dust only"""
        x = ev4.get(i)
        b0s = [foot4[r][0] for r in (x[2] if x and x[2] else []) if r in foot4 and foot4[r][1] == DUST_IDS[d]]
        return bool(b0s) and all(b == 3 for b in b0s)
    touched = set()
    for i in range(n):
        e = psl_entry(out, i)
        if e and any(e[1] >> k & 1 and e[3][k] == KIND_PEL_C and e[2][k] in DUST_IDS and gated(i, e[2][k])
                     for k in range(32)):
            touched.add(i)
    for i, x in ev4.items():
        if x[2] and any(r in known for r in x[2]):
            touched.add(i)
    for i in sorted(touched):
        assert i < n, ('motion past GU\'s PSL', bank, i)
        e = psl_entry(out, i)
        frames = evg[i][1]
        if e:
            assert e[0] == frames, ('PSL frames', bank, i)
            _, mask, ids, kinds, per = e
        else:
            mask, ids, kinds, per = 0, [0] * 32, [0] * 32, [0] * (frames - 1)
        dropped, added = [], []
        for k in range(32):
            if mask >> k & 1 and kinds[k] == KIND_PEL_C and ids[k] in DUST_IDS and gated(i, ids[k]):
                mask &= ~(1 << k); dropped.append(ids[k]); ids[k] = kinds[k] = 0
                per = [b & ~(1 << k) for b in per]
        x = ev4.get(i)
        if x and x[2]:
            _, frames4, remap, evs4 = x
            assert frames4 == frames, ('4U / GU frames', bank, i)
            per4 = [b for b, f in evs4 for _ in range(f)][:frames - 1]
            assert len(per4) == frames - 1, ('4U runs', bank, i)
            for k4, r in enumerate(remap):
                if r not in known: continue
                j = k4 if not (mask >> k4 & 1) else min(j for j in range(32) if not mask >> j & 1)
                mask |= 1 << j; ids[j] = r; kinds[j] = KIND_PEL_U
                per = [b | ((p >> k4 & 1) << j) for b, p in zip(per, per4)]
                added.append((r, j))
        psl_put(out, i, frames, mask, ids, kinds, per)
        log.append('PSL bank %d motion %d: GU dust %s out, em117_1 %s in' % (bank, i, dropped, added))
    return bytes(out)


def effects(S, gfile, code, notes):
    """em117's effects -> ([(path, type, data)], {field: (path, type)}): see above"""
    T4 = efl4u2gu.T
    own = efl4u2gu.mef_records(S[(MEF_OWN, T4['MEF'])])
    assert {r['id'] for r in own} == set(FOOT_IDS) | set(CAST_IDS) and all(r['grp'] == 117 for r in own), \
        'em117_1 records changed'
    for r in own:
        assert r['b0'] == (4 if r['id'] in FOOT_IDS else 0), ('em117_1 b0', r['id'])
        assert r['id'] not in FOOT_IDS or r['joint'] == FOOT_IDS[r['id']], ('stepfire joint', r['id'])
    gu_c = efl4u2gu.pel_lists(gfile(16))
    dust = {}
    i, body = 0, gu_c[1][1]
    while i < len(body):
        L = body[i]
        rid, joint = struct.unpack_from('<Hh', body, i + 1 + L + 2 + 0x30)
        if rid in DUST_IDS:
            dust[rid] = (joint, body[i + 1:i + 1 + L].decode())
        i += 1 + L + 2 + 160
    assert dust == {k: (j, 'effect\\cm\\cm202_020') for k, j in DUST_IDS.items()}, ('GU foot dust records', dust)
    gu_lists = efl4u2gu.pel_lists(gfile(17))
    extra2 = []
    for rid, grp, elem, k, follow, _ in CODE_FX:
        path = efl_4u(code, grp, elem)
        assert path.startswith('effect\\efl\\em\\em117\\em117_') and rid in CODE_FX_IDS, (rid, path)
        extra2.append((path, dict(id=rid, joint=-1, k=k, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scl=(1.0, 1.0, 1.0),
                                  follow=follow, world=not follow, once=False)))
    assert gu_world_tail() == efl4u2gu.PEL_TAIL_WORLD, "GU's world code-post tail (em001_00u record 31) changed"
    groups = {117: 'effect\\efl\\em\\em117\\em117_%03d'}
    spec = dict(arc=SRC_4U, stage_unpacked=[], mef=MEF_OWN, em_efl='effect\\efl\\em\\em117\\', groups=groups,
                extra=[], lmts=[], pel=PEL_U, soil=ingle_soil(notes), list2=gu_lists[2], extra2=extra2,
                hide_grey_models='chunks')
    log = []
    out = efl4u2gu.effect_set(spec, log)
    mine_lists = efl4u2gu.pel_lists(out.pop((PEL_U, T4['PEL'])))
    mine, list2 = mine_lists[1], mine_lists[2]
    known = set(pel_ids(mine[1]))
    assert known == {r['id'] for r in own}, ('converted em117_1 records', known)
    gu1 = pel_ids(gu_lists[1][1])
    assert not known & set(gu1), 'PEL list-1 ids collide with GU\'s'
    assert gu_lists[0][0] == 0, 'GU em013_01u list 0 not empty'
    ours2 = [r['id'] for _, r in extra2]
    assert not set(pel_ids(gu_lists[2][1])) & set(CODE_FX_IDS), 'PEL list-2 id block 4100..4199 not free'
    assert list2[0] == gu_lists[2][0] + len(CODE_FX) and pel_ids(list2[1]) == pel_ids(gu_lists[2][1]) + ours2, \
        'PEL list 2 = GU + ours'
    pel = b'PEL\0' + struct.pack('<II', 15, 0) + struct.pack('<I', gu_lists[1][0] + mine[0]) + gu_lists[1][1] + \
        mine[1] + struct.pack('<I', list2[0]) + list2[1]
    lists = efl4u2gu.pel_lists(pel)
    assert pel_ids(lists[1][1]) == gu1 + pel_ids(mine[1]) and lists[2] == list2, 'merged PEL u layout'
    ents =[(p, t, d) for (p, t), d in out.items()] + [(PEL_U, T4['PEL'], pel)]
    fields = {17: (PEL_U, T4['PEL'])}
    foot4 = {r['id']: (r['b0'], r['joint']) for r in efl4u2gu.mef_records(S[('effect\\mef\\em\\em077_0', T4['MEF'])])
             if r['joint'] in DUST_IDS.values()}
    assert {i for i, (b0, _) in foot4.items() if b0 == 3} == set(range(38, 48)), 'em077_0 gated dust records changed'
    plog = []
    for b in BANKS:
        psl = psl_own(gfile(18 + b), S[(P77 + 'mot\\em077_%d' % b, T4['LMT'])], gfile(4 + b), known, foot4, b, plog)
        ents.append((PSL % b, T4['PSL'], psl))
        fields[18 + b] = (PSL % b, T4['PSL'])
    notes.append('effects: PEL u = GU em013_01u (list 1: %d, list 2: %d) + em117_1 (%d) + code records %s (list 2); '
                 '%d converted 4U files' % (gu_lists[1][0], gu_lists[2][0], len(known), ours2, len(out)))
    notes += ['  ' + l for l in plog]
    notes += ['  ' + l for l in log if not l.startswith('EFL ')]
    notes += ['  code post %d: %s k %d %s; 4U %s' % (r['id'], p.split('\\')[-1], r['k'],
                                                     'follows its shell' if r['follow'] else 'world post', src)
              for (p, r), src in zip(extra2, [x[-1] for x in CODE_FX])]
    return ents, fields


def sound(rom, notes):
    """em117's sound call, waves, bank snd_em117 and request (tools/snd4u2gu.py monster_entries) -> ([(path, type,
    data)], {field: (path, type)}). Common-bank requests from GU em013_01 (same numbers in every GU monster), plus the
    ones GU's Crimson adds (its class may post them)."""
    spec = dict(name='em117', src=SRC_4U, p4_wave='sound\\se\\em\\em117\\wave\\',
                pg_wave='sound\\se\\em\\em013_06\\wav\\', p4_bank='sound\\se\\em\\em117\\snd_em117',
                pg_bank='sound\\se\\em\\em013_06\\snd_em013_06', p4_call='sound\\call\\em\\em117',
                pg_call='sound\\call\\em\\em013_06', donor_arc=GU_ARC, donor_name='GU em013_01', donor_extra=True)
    log = []
    out = snd4u2gu.monster_entries(spec, rom=rom, log=log)
    snd4u2gu.verify(out, spec)
    req = [d for p, t, d in out if (p, t) == (spec['pg_bank'], snd4u2gu.TG['REQ'])]
    assert len(req) == 1
    mine = {e[0] & 0xFFFF: e[21] for e in snd4u2gu.reqgu_parse(req[0])['ents']}
    _, gents = arcpack.read(rom.read(GU_ARC))
    gu_req = [d for p, t, d in gents if p == 'sound\\se\\em\\em013_01\\snd_em013_01' and t == snd4u2gu.TG['REQ']]
    assert len(gu_req) == 1
    gu_own = sorted(e[0] & 0xFFFF for e in snd4u2gu.reqgu_parse(gu_req[0])['ents'] if e[21] == 0)
    lacks = [i for i in gu_own if mine.get(i) != 0]
    notes += log
    notes.append('sound request: GU em013_01\'s own-bank requests em117 lacks (silent if GU code posts them): %s' % lacks)
    return out, {12: (spec['pg_call'], snd4u2gu.TG['CALL']), 13: (spec['pg_bank'], snd4u2gu.TG['REQ'])}


# ---- the new shells' family (data side; the classes are module/em013_06_shell*.c). Def = GU em013_01_shell01 (the
# family GU's row 135 names, param class EmBase01 = DTI 0x188cb88, our request's) under our path, by same-length renames
# only: the family path and the def's PEL path. Its kind files (ef / snd / hit / sh) stay GU's bytes under our path:
# our classes read only the hit data (slot 80 arms HDS entry k), as Dalamadur's and Gogmazios' families.
SHELL_SRC = 'shell\\em\\em013_01_shell01\\em013_01_01'
SHELL_DST = 'shell\\em\\em013_06_shell01\\em013_06_01'
T_HDS, T_HTS, T_SHELL = 0x4EB68CEE, 0x5653C1B0, 0x4AA69872
# 4U shell attack data (C): (40-B records, volume pointer table); record byte 0x19 = volume
U012 = (0x1028958, 0x1028904)    # uShell012 init 0xc61ab0: record = 0x10290b0[subtype]
U037 = (0x102f830, 0x102f808)    # uShell037 init 0xc836a8: record = 0x102f998[kind]
U003 = (0x101f230, 0x101efbc)    # uShell003 (dala_shell003.c): record = subtype
# HDS entries in the module's order (module em013_06_shell.h), byte 0x19 = the HTS group of the same index
SHELL_HDS = [('heatwave ahead (uShell012 51, record 35)', U012, 35), ('heatwave sides (uShell012 54 / 55, record 37)',
             U012, 37), ('heatwave ahead, event (uShell012 66, record 45)', U012, 45),
             ('heatwave sides, event (uShell012 67 / 68, record 46)', U012, 46),
             ('eruption (uShell037 8, record 6)', U037, 6), ('stepfire (uShell003 177)', U003, 177)]


def shell_hds_hts(code, gu_hds, gu_hts, notes):
    """our HDS / HTS from the 4U records (the em089 rule, hds_rule / hts_rule, 4U's +4 kept: Capcom set it per volume,
    e.g. 1 on Stygian's pillar, 0 on Kushala's bone-1001 shot, no rule to follow)"""
    assert gu_hds[:4] == b'HDS\0' and gu_hts[:4] == b'HTS\0'
    n = struct.unpack_from('<I', gu_hts, 8)[0]
    tab = [struct.unpack_from('<II', gu_hts, 16 + 8 * k) for k in range(n)]
    recs = [gu_hts[o + 48 * j:o + 48 * (j + 1)] for c, o in tab for j in range(c)]
    hds, hts = [], []
    for k, (name, sh, i) in enumerate(SHELL_HDS):
        r4 = rec_4u(code, sh, i)
        v4 = vol_4u(code, sh, r4[0x19])
        hds.append(hds_rule(r4, k))
        hts.append(hts_rule(v4, recs[0]))
        h = hts[-1]
        notes.append('  HDS %d %s: window %d+%d power %d type 0x%x level %d -> HTS %d: volume %d bone %d +4 %d r%g' % (
            k, name, *struct.unpack_from('<hHH', hds[-1], 0), hds[-1][6], hds[-1][0x2c], k, r4[0x19],
            struct.unpack_from('<H', h, 0)[0], h[4], struct.unpack_from('<f', h, 0x0c)[0]))
    d_hds = struct.pack('<4sIII', b'HDS\0', struct.unpack_from('<I', gu_hds, 4)[0], len(hds), 0) + b''.join(hds)
    head = bytearray(gu_hts[:16])
    struct.pack_into('<I', head, 8, len(hts))
    table = b''.join(struct.pack('<II', 1, 16 + 8 * len(hts) + 48 * k) for k in range(len(hts)))
    return d_hds, bytes(head) + table + b''.join(hts)


def shell_family(gents, code, notes):
    """[(path, type, data)] of our family in GU's order (def last)"""
    assert len(SHELL_SRC) == len(SHELL_DST) and len(PEL_GU) == len(PEL_U)
    src = [(p, t, d) for p, t, d in gents if p.startswith(SHELL_SRC)]
    by_t = {t: d for p, t, d in src if t in (T_HDS, T_HTS)}
    hds, hts = shell_hds_hts(code, by_t[T_HDS], by_t[T_HTS], notes)
    out = []
    for p, t, d in src:
        if t == T_SHELL:
            assert d.count(PEL_GU.encode()) == 1, 'def PEL path'
            d = d.replace(SHELL_SRC.encode(), SHELL_DST.encode()).replace(PEL_GU.encode(), PEL_U.encode())
            assert b'em013_01_shell01' not in d
        elif t == T_HDS:
            d = hds
        elif t == T_HTS:
            d = hts
        else:
            assert b'em013' not in d and b'shell\\' not in d, p
        out.append((SHELL_DST + p[len(SHELL_SRC):], t, d))
    assert out[-1][:2] == (SHELL_DST, T_SHELL) and sum(t == T_SHELL for _, t, _ in out) == 1, 'def not last'
    notes.append('shell family %s: %d files from GU %s (PEL %s); HDS / HTS: %d entries' % (
        SHELL_DST, len(out), SHELL_SRC, PEL_U, len(SHELL_HDS)))
    return out


def main():
    img = open(paths.GU_MAIN, 'rb').read()
    code = open(CODE_4U, 'rb').read()
    rom = RomFS(paths.GU_ROMFS)
    _, src = arcpack.read(open(SRC_4U, 'rb').read())
    S = {(p, t): d for p, t, d in src}
    _, gents = arcpack.read(rom.read(GU_ARC))
    notes = []
    ghash = {(phash(p), t): (p, t) for p, t, _ in gents}
    gman = manifest_of(img, ALLOC['donor_index'])
    G = {(p, t): d for p, t, d in gents}
    gfile = lambda k: G[ghash[fileid_entry(img, gman[k])]]          # GU em013_01's file of manifest field k
    gtype = lambda k: ghash[fileid_entry(img, gman[k])][1]
    shared_4u(S, notes)

    # ---- our own files
    own, ents = {}, []
    files, m4 = model(S, rom, notes)
    ents += files
    own[0] = (P + 'mod\\em013_06', T['MOD'])
    groups = sorted({x['group'] for x in m4['mesh_list']})
    ents.append((P + 'mod\\em013_06', T['XFS'], parts_xfs(gfile(3), gfile(0), groups, notes)))
    own[3] = (P + 'mod\\em013_06', T['XFS'])
    files, fields = sound(rom, notes)
    ents += files
    own.update(fields)
    files, fields = effects(S, gfile, code, notes)
    ents += files
    own.update(fields)
    dtbase_check(gfile(32), notes)
    ents.append(('enemy\\dt_tune\\em013_06_dttune', gtype(33), dttune(gfile(33), notes)))
    own[33] = ('enemy\\dt_tune\\em013_06_dttune', gtype(33))
    ents.append(('enemy\\cmd_tbl\\em013_06_cmdtbl', gtype(37), cmdtbl(S[(P77 + 'data\\em077_cmd', T['EMC'])], gfile(37),
                                                                      img, notes)))
    own[37] = ('enemy\\cmd_tbl\\em013_06_cmdtbl', gtype(37))
    sys.path.insert(0, HERE)
    import hagi_em013_06
    for k, data in hagi_em013_06.files().items():
        path = 'enemy\\hagi\\hagi_s%d_em013_06' % (k - 46)
        ents.append((path, gtype(k), data))
        own[k] = (path, gtype(k))
    notes.append('carves: 4U em117 G table in hagi s4 (tools/hagi_em013_06.py)')

    # ---- the shared GU em013_01 files: everything but what ours replace, em013_01's model and its sound bank's waves
    replaced = {ghash[fileid_entry(img, gman[k])] for k in own if gman[k] != -1}
    drop = replaced | {(p, t) for p, t, _ in gents if p.startswith(P1 + 'mod\\') or
                       p.startswith('sound\\se\\em\\em013_01\\')}
    while True:                                  # a file a kept one names by path stays
        kept = [(p, t, d) for p, t, d in gents if (p, t) not in drop]
        named = {(p, t) for p, t in drop if any(p.encode('ascii') in kd for _, _, kd in kept)}
        if not named: break
        for p, t in sorted(named):
            notes.append('kept %s although replaced: named by %s' % (p, [kp for kp, _, kd in kept
                                                                         if p.encode('ascii') in kd][:4]))
        drop -= named
    notes.append('shared from em013_01: %d files kept, %d dropped (replaced, its model, its sound bank)' % (
        len(kept), len(drop)))

    # ---- extras (no manifest field): the BGM STQR, the shell family (after GU's kept files: what it names comes first)
    extras = {'bgm_stqr': (BGM_STQR, T_STQR)}
    ext = [(BGM_STQR, T_STQR, open(BGM_STQR_SRC, 'rb').read())]
    fam = shell_family(gents, code, notes)
    extras['shell01'] = (SHELL_DST, T_SHELL)
    ents = ents + kept + ext + fam

    # ---- manifest: own fields -> our IDs (field order: IDs only ever grow), then the extras; the rest = em013_01's
    new_files, manifest, src_of = [], list(gman), {}
    assert set(own) <= set(OWN_ORDER), 'add new own fields at the end of OWN_ORDER: %s' % (set(own) - set(OWN_ORDER))
    for k in [k for k in OWN_ORDER if k in own]:
        fid = FILE_ID_BASE + len(new_files)
        new_files.append((fid,) + own[k])
        manifest[k] = fid
        src_of[k] = 'converted (4U em117)'
    extra_ids = {}
    for name in EXTRA_ORDER:
        fid = FILE_ID_BASE + len(new_files)
        new_files.append((fid,) + extras[name])
        extra_ids[name] = fid
    assert new_files[-1][0] <= FILE_ID_LAST, 'file IDs past the allocations.toml range: widen file_ids'
    for k in range(51):
        if k not in own and manifest[k] != -1: src_of[k] = 'shared (GU em013_01, its file ID)'

    # ---- verify before writing anything
    arc = arcpack.build(ents)
    ver, back = arcpack.read(arc)
    assert ver == 0x11 and len(back) == len(ents)
    assert len({(p, t) for p, t, _ in back}) == len(back), 'duplicate entries'
    present = {(phash(p), t) for p, t, _ in back}
    for fid, p, t in new_files:
        assert (phash(p), t) in present, p
    for k in range(51):
        if manifest[k] != -1 and manifest[k] < FILE_ID_BASE:
            assert fileid_entry(img, manifest[k]) in present, (k, hex(manifest[k]))
    for p, t, d in back:
        if p.startswith(P) and t == T['MOD']: modlib.parse(d)
        if p.startswith(P) and t == T['TEX']: tex.decode(d)

    # ---- write
    os.makedirs(os.path.dirname(OUT_ARC), exist_ok=True)
    open(OUT_ARC, 'wb').write(arc)
    fields = []
    for k in range(51):
        fid = manifest[k]
        if fid == -1:
            fields.append(dict(field=k, file_id=-1)); continue
        p, t = new_files[fid - FILE_ID_BASE][1:] if fid >= FILE_ID_BASE else ghash[fileid_entry(img, fid)]
        fields.append(dict(field=k, file_id='0x%x' % fid, path=p, type='0x%08x' % t, source=src_of[k]))
    json.dump(dict(monster='em013_06 (G-rank Crimson Fatalis)', id='0x%x' % ALLOC['em_id'],
                   registry_index=ALLOC['registry_index'], file_id_base='0x%x' % FILE_ID_BASE,
                   file_count=len(new_files), manifest=fields, **{k: '0x%x' % v for k, v in extra_ids.items()},
                   files=[dict(file_id='0x%x' % f, path=p, type='0x%08x' % t, path_hash='0x%08x' % phash(p))
                          for f, p, t in new_files], notes=notes),
              open(OUT_JSON, 'w', encoding='utf-8', newline='\n'), indent=1)    # LF on every OS (.gitattributes)
    # FILE section: the registry manifest of its index and the (path hash, type) of each of our file IDs
    sec = portdata.Section('FILE')
    sec.u32(FILE_ID_BASE, len(new_files), *[x & 0xFFFFFFFF for x in manifest])
    for fid, p, t in new_files:
        sec.u32(phash(p), t)
    print('wrote', portdata.write_section(NAME, sec))
    print('arc: %d entries, %.1f MB -> %s' % (len(ents), len(arc) / 1e6, OUT_ARC))
    print('own file IDs 0x%x..0x%x (%d), extras %s' % (FILE_ID_BASE, FILE_ID_BASE + len(new_files) - 1, len(new_files),
                                                      {k: hex(v) for k, v in extra_ids.items()}))
    for n in notes: print(' ', n)


if __name__ == '__main__':
    main()
