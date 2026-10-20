# Fusion なしで「似ているもの」の判定を試す。
# 使い方: python tools/test_similar.py "<作業フォルダ>\<ハブ名>"
import collections
import json
import os
import sys
import time
import types

# adsk を空のモジュールで代用して sorter_core を読み込む
adsk = types.ModuleType('adsk')
adsk.core = types.ModuleType('adsk.core')
adsk.fusion = types.ModuleType('adsk.fusion')
adsk.doEvents = lambda: None
sys.modules.update({'adsk': adsk, 'adsk.core': adsk.core, 'adsk.fusion': adsk.fusion})
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import sorter_core as core  # noqa: E402

wdir = sys.argv[1]
inv = json.load(open(os.path.join(wdir, 'inventory.json'), encoding='utf-8'))
items = inv['items']
for it in items:
    it.pop('look', None)
t = time.time()
core.ensure_hashes(items, wdir)
print(f'ハッシュ {len(items)}件 {time.time() - t:.1f}秒')
core.find_similar(items)
out = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_similar_out.txt'), 'w', encoding='utf-8')
for key, label in (('simName', '名前が似ている'), ('simLook', '見た目が似ている')):
    g = collections.defaultdict(list)
    for it in items:
        if it[key]:
            g[it[key]].append(it['loc'] + '/' + it['name'])
    print(label, len(g), 'グループ', file=out)
    for k, v in g.items():
        print('  ', ' | '.join(v), file=out)
print('出力:', out.name)
