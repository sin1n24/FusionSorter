# Fusion なしでサイズによる同一判定を試す（既存の書き出し結果のサイズを流用）。
# 使い方: python tools/test_size_dup.py "<作業フォルダ>\<ハブ名>" "<書き出し先>\<ハブ名>"
import os
import sys
import types

adsk = types.ModuleType('adsk')
adsk.core = types.ModuleType('adsk.core')
adsk.fusion = types.ModuleType('adsk.fusion')
adsk.doEvents = lambda: None
sys.modules.update({'adsk': adsk, 'adsk.core': adsk.core, 'adsk.fusion': adsk.fusion})
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import json  # noqa: E402
import sorter_core as core  # noqa: E402

wdir, out = sys.argv[1], sys.argv[2]
inv = json.load(open(os.path.join(wdir, 'inventory.json'), encoding='utf-8'))
items = inv['items']
used = set()
for it in items:
    base = os.path.join(out, *[core.safe(x) for x in it['loc'].split('/')], core.safe(it['name']))
    p, k = base + '.f3d', 2
    while p.lower() in used:
        p, k = f'{base} ({k}).f3d', k + 1
    used.add(p.lower())
    if it['ext'] == 'f3d' and os.path.exists(p):
        it['size'] = os.path.getsize(p)
print('サイズあり', sum(1 for it in items if it.get('size')), '/', len(items))
print('サイズで DEL にした件数', core.size_duplicates(items))
for it in items:
    w = it.get('why')
    if isinstance(w, dict) and w.get('k') == 'dupSize':
        print(' ', it['loc'], it['name'], it['why'])
core.ensure_hashes(items, wdir)
core.find_similar(items)
g = {}
for it in items:
    if it.get('simSize'):
        g.setdefault(it['simSize'], []).append(it['loc'] + '/' + it['name'])
print('名前違いでサイズが近い', len(g), '組')
for v in g.values():
    print('  ', ' | '.join(v))
