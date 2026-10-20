# ThumbSorterの処理本体。画面からの要求(action)ごとに handle() で振り分ける。
#
# 作業フォルダ（既定: ドキュメント\FusionSorter\<ハブ名>）に置くもの:
#   inventory.json  ハブの一覧（読み込み時に作成）
#   plan.json       画面で決めた行き先（自動保存）
#   thumbs\         クラウドのサムネイル(256px PNG)
#   moves_*.csv     移動の記録（元に戻すときに使う）
# 削除は一切しない。「削除」は最上位の DEL プロジェクトへの移動として扱う。

import adsk.core
import adsk.fusion
import base64
import csv
import datetime
import hashlib
import json
import os
import re
import shutil
import time
import unicodedata
import webbrowser
import zlib

app = None
ui = None
WORK_ROOT = os.path.join(os.path.expanduser('~'), 'Documents', 'FusionSorter')
DEL = 'DEL'
PENDING = 0   # 画面上で仕分けたがハブにまだ反映していない件数（パレットを閉じたときの警告用）


def init(a, u):
    global app, ui
    app, ui = a, u


# ---------- 共通 ----------

def safe(name):
    name = re.sub(r'[\\/:*?"<>|]', '_', name or '').strip().rstrip('.')
    return name or '_'


def ymd(t):
    try:
        return datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d') if t else ''
    except Exception:
        return ''


def hub_by_id(hub_id):
    hubs = app.data.dataHubs
    for i in range(hubs.count):
        if hubs.item(i).id == hub_id:
            return hubs.item(i)
    raise RuntimeError('ハブが見つかりません')


def work_dir(hub):
    d = os.path.join(WORK_ROOT, safe(hub.name))
    os.makedirs(os.path.join(d, 'thumbs'), exist_ok=True)
    return d


def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def walk(hub, progress=None):
    """ハブ全体を走査して (場所, DataFile) を返す。場所は 'プロジェクト/フォルダ/…'"""
    out = []
    projects = hub.dataProjects
    for p in range(projects.count):
        proj = projects.item(p)
        stack = [(proj.rootFolder, proj.name)]
        while stack:
            folder, loc = stack.pop()
            files = folder.dataFiles
            for i in range(files.count):
                out.append((loc, files.item(i)))
                if progress and len(out) % 20 == 0:
                    progress(len(out))
            subs = folder.dataFolders
            for i in range(subs.count):
                sub = subs.item(i)
                stack.append((sub, loc + '/' + sub.name))
        adsk.doEvents()
    return out


def folder_paths(hub):
    """ハブ内の全フォルダの場所（空のフォルダも含む）"""
    paths = []
    projects = hub.dataProjects
    for p in range(projects.count):
        proj = projects.item(p)
        stack = [(proj.rootFolder, proj.name)]
        while stack:
            folder, loc = stack.pop()
            paths.append(loc)
            subs = folder.dataFolders
            for i in range(subs.count):
                sub = subs.item(i)
                stack.append((sub, loc + '/' + sub.name))
    return paths


# ---------- 読み込み ----------

def fetch_thumbs(items, wdir, send):
    """クラウドのサムネイルを並行して取得する（デザインは開かない）。結果の内訳を返し、thumb_log.txt に残す"""
    todo = [it for it in items if not os.path.exists(os.path.join(wdir, 'thumbs', it['thumb']))]
    total, done = len(todo), 0
    stats = {'保存': 0, 'サムネなし': 0, '時間切れ': 0, 'エラー': 0}
    errors = []
    BATCH = 16

    def save(it, fu):
        # saveToFile は日本語パスで失敗することがあるため、base64 で受け取って Python で書く
        data = fu.dataObject.getAsBase64String()
        if not data:
            raise RuntimeError('空のデータ')
        with open(os.path.join(wdir, 'thumbs', it['thumb']), 'wb') as f:
            f.write(base64.b64decode(data))

    for b in range(0, total, BATCH):
        futures = []
        for it in todo[b:b + BATCH]:
            try:
                futures.append((it, it['_df'].thumbnail))
            except Exception as e:
                stats['エラー'] += 1
                errors.append(f'{it["loc"]}/{it["name"]}: thumbnail取得開始 {e}')
                done += 1
        deadline = time.time() + 60
        while futures and time.time() < deadline:
            rest = []
            for it, fu in futures:
                st = fu.state
                if st == adsk.core.FutureStates.ProcessingFutureState:
                    rest.append((it, fu))
                    continue
                if st == adsk.core.FutureStates.FinishedFutureState and fu.dataObject:
                    try:
                        save(it, fu)
                        stats['保存'] += 1
                    except Exception as e:
                        stats['エラー'] += 1
                        errors.append(f'{it["loc"]}/{it["name"]}: 保存 {e}')
                else:
                    stats['サムネなし'] += 1
                    errors.append(f'{it["loc"]}/{it["name"]}: state={st}')
                done += 1
            futures = rest
            adsk.doEvents()
            time.sleep(0.05)
        for it, fu in futures:
            stats['時間切れ'] += 1
            errors.append(f'{it["loc"]}/{it["name"]}: 60秒で取得できず')
        done += len(futures)
        send('progress', {'phase': 'サムネイル取得', 'done': done, 'total': total})
    with open(os.path.join(wdir, 'thumb_log.txt'), 'w', encoding='utf-8') as f:
        f.write(datetime.datetime.now().isoformat(timespec='seconds') + ' ' + json.dumps(stats, ensure_ascii=False) + '\n')
        f.write('\n'.join(errors))
    return stats


# ---------- 似ているものの判定 ----------
# クラウドの一覧からはファイルサイズが取れないため、「名前」と「サムネイルの見た目」で判定する。
# どちらも候補として示すだけで、自動で DEL にはしない。

def png_gray(path):
    """PNG(8bit, RGB/RGBA/グレー)をグレースケールの行リストにする。外部ライブラリなし"""
    with open(path, 'rb') as f:
        b = f.read()
    if b[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('PNGではない')
    i, idat, w, h, ctype = 8, b'', 0, 0, 0
    while i < len(b):
        n = int.from_bytes(b[i:i + 4], 'big')
        t = b[i + 4:i + 8]
        d = b[i + 8:i + 8 + n]
        if t == b'IHDR':
            w, h = int.from_bytes(d[0:4], 'big'), int.from_bytes(d[4:8], 'big')
            if d[8] != 8 or d[12] != 0:
                raise ValueError('未対応のPNG')
            ctype = d[9]
        elif t == b'IDAT':
            idat += d
        i += 12 + n
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}.get(ctype)
    if not bpp:
        raise ValueError('未対応の色形式')
    raw = zlib.decompress(idat)
    stride = w * bpp
    prev = bytearray(stride)
    rows = []
    pos = 0
    for _ in range(h):
        ft = raw[pos]
        cur = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ft == 1:
            for x in range(bpp, stride):
                cur[x] = (cur[x] + cur[x - bpp]) & 255
        elif ft == 2:
            for x in range(stride):
                cur[x] = (cur[x] + prev[x]) & 255
        elif ft == 3:
            for x in range(stride):
                a = cur[x - bpp] if x >= bpp else 0
                cur[x] = (cur[x] + ((a + prev[x]) >> 1)) & 255
        elif ft == 4:
            for x in range(stride):
                a = cur[x - bpp] if x >= bpp else 0
                c = prev[x - bpp] if x >= bpp else 0
                bb = prev[x]
                p = a + bb - c
                pa, pb, pc = abs(p - a), abs(p - bb), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (bb if pb <= pc else c)
                cur[x] = (cur[x] + pr) & 255
        rows.append(cur)
        prev = cur
    gray = []
    for r in rows:
        if bpp >= 3:
            line = []
            for x in range(0, stride, bpp):
                v = (r[x] * 3 + r[x + 1] * 6 + r[x + 2]) // 10
                if bpp == 4:   # 透明は白とみなす
                    al = r[x + 3]
                    v = (v * al + 255 * (255 - al)) // 255
                line.append(v)
        else:
            line = [r[x] for x in range(0, stride, bpp)]
        gray.append(line)
    return w, h, gray


def dhash(path):
    """差分ハッシュ(64bit)。9×8 に縮めて隣どうしの明暗を比べる"""
    w, h, g = png_gray(path)
    small = []
    for yy in range(8):
        y0, y1 = yy * h // 8, (yy + 1) * h // 8
        row = []
        for xx in range(9):
            x0, x1 = xx * w // 9, (xx + 1) * w // 9
            s = cnt = 0
            for y in range(y0, y1, 2):
                line = g[y]
                for x in range(x0, x1, 2):
                    s += line[x]
                    cnt += 1
            row.append(s // max(cnt, 1))
        small.append(row)
    bits = 0
    for row in small:
        for xx in range(8):
            bits = (bits << 1) | (1 if row[xx] > row[xx + 1] else 0)
    return bits


def ensure_hashes(items, wdir, send=None):
    """サムネイルの見た目ハッシュを item['look'] に入れる（作成済みは飛ばす）。変更があれば True"""
    todo = [it for it in items if 'look' not in it and os.path.exists(os.path.join(wdir, 'thumbs', it['thumb']))]
    for n, it in enumerate(todo, 1):
        try:
            it['look'] = '%016x' % dhash(os.path.join(wdir, 'thumbs', it['thumb']))
        except Exception:
            it['look'] = ''
        if send and n % 10 == 0:
            send('progress', {'phase': '見た目の比較準備', 'done': n, 'total': len(todo)})
            adsk.doEvents()
    return bool(todo)


NAME_TAIL = re.compile(r'([\s_\-\.]*(\(\d+\)|v\d+|ver\.?\d+|rev\d+|copy|コピー|\d+)|[\s_\-]+(old|new|旧|新))+$', re.I)


def norm_name(name):
    """末尾の番号・版・コピー表記などを落とした比較用の名前"""
    n = unicodedata.normalize('NFKC', name).strip().lower()
    base = NAME_TAIL.sub('', n)
    base = re.sub(r'[\s_\-\.]+', '', base)
    return base if len(base) >= 3 else re.sub(r'[\s_\-\.]+', '', n)


LOOK_DIST = 2   # 見た目ハッシュの違いがこのビット数以下なら「似ている」


def find_similar(items):
    """似た名前のグループ(simName)と、見た目が似ているグループ(simLook)を付ける"""
    for it in items:
        it['simName'] = 0
        it['simLook'] = 0
        it['simSize'] = 0
    groups = {}
    for it in items:
        groups.setdefault(norm_name(it['name']), []).append(it)
    gid = 0
    for g in groups.values():
        names = {x['name'].strip().lower() for x in g}
        if len(g) >= 2 and len(names) >= 2:   # 完全に同じ名前だけの組は「重複」タブで扱う
            gid += 1
            for x in g:
                x['simName'] = gid
    # 見た目: ハミング距離が小さいものをつなぐ（Union-Find）
    hs = [(it, int(it['look'], 16)) for it in items if it.get('look')]
    parent = list(range(len(hs)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for i in range(len(hs)):
        hi = hs[i][1]
        if hi in (0, 0xffffffffffffffff):
            continue   # 真っ白などは比較しない
        for j in range(i + 1, len(hs)):
            if bin(hi ^ hs[j][1]).count('1') <= LOOK_DIST:
                parent[find(i)] = find(j)
    # 書き出し済みなら、名前が違ってもサイズがほぼ同じで見た目も近いものを候補にする
    sized = sorted([it for it in items if it.get('size', 0) >= 10000], key=lambda x: x['size'])
    sid = 0
    for i, a in enumerate(sized):
        for b in sized[i + 1:]:
            if not size_close(a['size'], b['size'], 0.003):
                break
            if a['name'].strip().lower() == b['name'].strip().lower() or a['ext'] != b['ext']:
                continue
            # サイズだけだと偶然の一致が多いので、見た目もほぼ同じものに限る
            if not (a.get('look') and b.get('look')) or bin(int(a['look'], 16) ^ int(b['look'], 16)).count('1') > LOOK_DIST + 2:
                continue
            g = a.get('simSize') or b.get('simSize') or 0
            if not g:
                sid += 1
                g = sid
            a['simSize'] = b['simSize'] = g
    clusters = {}
    for i, (it, _) in enumerate(hs):
        clusters.setdefault(find(i), []).append(it)
    gid = 0
    for c in clusters.values():
        if 2 <= len(c) <= 12:   # 大きすぎる塊は単純な形どうしの偶然の一致とみなして出さない
            gid += 1
            for x in c:
                x['simLook'] = gid


SIZE_TOL = 0.02   # f3d は書き出すたびに中身が少し変わる（同じデザインでもサイズが±1%ほど揺れる）ため幅を持たせる


def size_close(a, b, tol):
    return a and b and abs(a - b) / max(a, b) < tol


def size_duplicates(items):
    """書き出したサイズで同一を判定。同名でサイズ差2%未満なら同じ内容とみなし、版数の多い方を残して他を DEL にする"""
    groups = {}
    for it in items:
        if it.get('size'):
            groups.setdefault((it['name'].strip().lower(), it['ext']), []).append(it)
    count = 0
    for g in groups.values():
        if len(g) < 2:
            continue
        g.sort(key=lambda x: (x['ver'], x['modified']), reverse=True)
        clusters = []
        for it in g:
            for c in clusters:
                if size_close(c[0]['size'], it['size'], SIZE_TOL):
                    c.append(it)
                    break
            else:
                clusters.append([it])
        for c in clusters:
            keeper = c[0]
            for x in c[1:]:
                if x['init'] != DEL:
                    x['init'] = DEL
                    x['why'] = f'重複: 「{keeper["loc"]}」の同名(v{keeper["ver"]})と書き出したファイルサイズがほぼ同じ（差{abs(x["size"] - keeper["size"]) * 100 / keeper["size"]:.1f}%）'
                    count += 1
    return count


def find_duplicates(items, wdir):
    """同名グループを作り、サムネイルが完全に同じものは版数の多い方を残して他を DEL 候補にする"""
    groups = {}
    for it in items:
        groups.setdefault((it['name'].strip().lower(), it['ext']), []).append(it)
    gid = 0
    for g in groups.values():
        if len(g) < 2:
            continue
        gid += 1
        hashes = {}
        for it in g:
            it['dup'] = gid
            p = os.path.join(wdir, 'thumbs', it['thumb'])
            h = ''
            if os.path.exists(p):
                with open(p, 'rb') as f:
                    h = hashlib.md5(f.read()).hexdigest()
            hashes.setdefault(h, []).append(it)
        for h, same in hashes.items():
            if not h or len(same) < 2:
                continue
            same.sort(key=lambda x: (x['ver'], x['modified']), reverse=True)
            keeper = same[0]
            for x in same[1:]:
                x['init'] = DEL
                x['why'] = f'重複: 「{keeper["loc"]}」の同名(v{keeper["ver"]})とサムネイルが完全に同じ'
    return gid


def scan(data, send):
    hub = hub_by_id(data['hubId'])
    wdir = work_dir(hub)
    inv_path = os.path.join(wdir, 'inventory.json')
    if not data.get('reload') and os.path.exists(inv_path):
        inv = load_json(inv_path, None)
        if inv:
            if ensure_hashes(inv['items'], wdir, send):   # 旧版の一覧には見た目ハッシュが無い
                save_json(inv_path, inv)
            return result_payload(hub, wdir, inv)
    if data.get('cacheOnly'):
        return None   # 前回の一覧が無い。画面側で「ハブから取得」を促す

    app.data.activeHub = hub
    send('progress', {'phase': 'ハブを走査中', 'done': 0, 'total': 0})
    pairs = walk(hub, lambda n: send('progress', {'phase': 'ハブを走査中', 'done': n, 'total': 0}))
    items = []
    for loc, df in pairs:
        items.append({
            'id': df.id, 'name': df.name, 'ext': (df.fileExtension or '').lower(),
            'ver': df.versionNumber, 'created': ymd(df.dateCreated), 'modified': ymd(df.dateModified),
            'loc': loc, 'init': loc, 'why': '', 'dup': 0,
            'thumb': hashlib.md5(df.id.encode('utf-8')).hexdigest() + '.png', '_df': df,
        })
    thumb_stats = fetch_thumbs(items, wdir, send)
    for it in items:
        it.pop('_df', None)
    ensure_hashes(items, wdir, send)
    ngroups = find_duplicates(items, wdir)
    inv = {'hub': hub.name, 'hubId': hub.id, 'scanned': datetime.datetime.now().isoformat(timespec='seconds'),
           'items': items, 'folders': folder_paths(hub), 'dupGroups': ngroups,
           'thumbStats': thumb_stats}
    save_json(inv_path, inv)
    # 走査し直したら、場所が変わったものの手入力は残す（id で対応）
    return result_payload(hub, wdir, inv)


def result_payload(hub, wdir, inv):
    plan = load_json(os.path.join(wdir, 'plan.json'), {'dest': {}, 'folders': []})
    find_similar(inv['items'])
    return {'hub': hub.name, 'hubId': hub.id, 'workDir': wdir.replace('\\', '/'),
            'scanned': inv.get('scanned'), 'items': inv['items'], 'folders': inv.get('folders', []),
            'plan': plan, 'thumbStats': inv.get('thumbStats')}


# ---------- 実行: 同じハブ内で移動 ----------

def resolve_folder(hub, path, cache, created):
    """'プロジェクト/フォルダ/…' のフォルダを取得。無ければ作る"""
    if path in cache:
        return cache[path]
    parts = path.split('/')
    projects = hub.dataProjects
    proj = None
    for i in range(projects.count):
        if projects.item(i).name == parts[0]:
            proj = projects.item(i)
            break
    if proj is None:
        proj = projects.add(parts[0])
        if not proj:
            raise RuntimeError(f'プロジェクト「{parts[0]}」を作れませんでした')
        created.append(parts[0])
    folder = proj.rootFolder
    cur = parts[0]
    for name in parts[1:]:
        cur += '/' + name
        if cur in cache:
            folder = cache[cur]
            continue
        sub = folder.dataFolders.itemByName(name)
        if not sub:
            sub = folder.dataFolders.add(name)
            if not sub:
                raise RuntimeError(f'フォルダ「{cur}」を作れませんでした')
            created.append(cur)
        folder = sub
        cache[cur] = folder
    cache[path] = folder
    return folder


def planned_moves(inv, plan):
    moves = []
    for it in inv['items']:
        dest = plan['dest'].get(it['id'], it['init'])
        if dest and dest != it['loc']:
            moves.append((it, dest))
    return moves


def preview(data, send):
    hub = hub_by_id(data['hubId'])
    wdir = work_dir(hub)
    inv = load_json(os.path.join(wdir, 'inventory.json'), None)
    plan = load_json(os.path.join(wdir, 'plan.json'), {'dest': {}, 'folders': []})
    if not inv:
        raise RuntimeError('先に読み込んでください')
    moves = planned_moves(inv, plan)
    existing = set(inv.get('folders', []))
    new_folders = set()
    for _, dest in moves:
        parts = dest.split('/')
        for i in range(1, len(parts) + 1):
            p = '/'.join(parts[:i])
            if p not in existing:
                new_folders.add(p)
    return {'moves': [{'name': it['name'], 'from': it['loc'], 'to': d} for it, d in moves],
            'newFolders': sorted(new_folders)}


def execute_move(data, send):
    hub = hub_by_id(data['hubId'])
    wdir = work_dir(hub)
    inv_path = os.path.join(wdir, 'inventory.json')
    inv = load_json(inv_path, None)
    plan = load_json(os.path.join(wdir, 'plan.json'), {'dest': {}, 'folders': []})
    moves = planned_moves(inv, plan)
    if not moves:
        return {'moved': 0, 'failed': 0, 'log': ''}
    app.data.activeHub = hub
    send('progress', {'phase': '現在の状態を確認中', 'done': 0, 'total': 0})
    by_id = {df.id: (loc, df) for loc, df in walk(hub)}
    cache, created = {}, []
    log_path = os.path.join(wdir, 'moves_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.csv')
    moved = failed = 0
    with open(log_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['id', '名前', '移動前', '移動後', '結果'])
        for n, (it, dest) in enumerate(moves, 1):
            res = ''
            cur = by_id.get(it['id'])
            if not cur:
                res = '見つからない(削除済み?)'
            elif cur[0] == dest:
                res = 'すでに移動済み'
            else:
                try:
                    folder = resolve_folder(hub, dest, cache, created)
                    ok = cur[1].move(folder)
                    res = 'OK' if ok else '失敗(開いている/参照されている可能性)'
                except Exception as e:
                    res = '失敗: ' + str(e)[:150]
            if res in ('OK', 'すでに移動済み'):
                moved += 1
                it['loc'] = dest
                it['init'] = dest
                plan['dest'].pop(it['id'], None)
            else:
                failed += 1
            w.writerow([it['id'], it['name'], cur[0] if cur else it['loc'], dest, res])
            f.flush()
            send('progress', {'phase': '移動中', 'done': n, 'total': len(moves)})
            adsk.doEvents()
    inv['folders'] = sorted(set(inv.get('folders', [])) | set(created) | set(cache.keys()))
    save_json(inv_path, inv)
    save_json(os.path.join(wdir, 'plan.json'), plan)
    return {'moved': moved, 'failed': failed, 'created': created, 'log': log_path.replace('\\', '/')}


def undo_move(data, send):
    """最後の移動の記録を逆にたどって元の場所へ戻す"""
    hub = hub_by_id(data['hubId'])
    wdir = work_dir(hub)
    logs = sorted(x for x in os.listdir(wdir) if x.startswith('moves_') and x.endswith('.csv') and '_undone' not in x)
    if not logs:
        raise RuntimeError('元に戻せる移動の記録がありません')
    last = os.path.join(wdir, logs[-1])
    with open(last, encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['結果'] == 'OK']
    app.data.activeHub = hub
    by_id = {df.id: (loc, df) for loc, df in walk(hub)}
    cache, created = {}, []
    back = failed = 0
    for n, r in enumerate(rows, 1):
        cur = by_id.get(r['id'])
        try:
            if cur and cur[0] != r['移動前']:
                if cur[1].move(resolve_folder(hub, r['移動前'], cache, created)):
                    back += 1
                else:
                    failed += 1
        except Exception:
            failed += 1
        send('progress', {'phase': '元に戻し中', 'done': n, 'total': len(rows)})
    os.replace(last, last[:-4] + '_undone.csv')
    return {'back': back, 'failed': failed}


# ---------- 実行: 仕分けた形で書き出す ----------

def execute_export(data, send):
    hub = hub_by_id(data['hubId'])
    wdir = work_dir(hub)
    out_root = data.get('outDir') or ''
    layout = data.get('layout', 'sorted')   # 'current' = 今の構成のまま全部 / 'sorted' = 仕分け後の構成
    if not out_root:
        raise RuntimeError('書き出し先を選んでください')
    inv = load_json(os.path.join(wdir, 'inventory.json'), None)
    plan = load_json(os.path.join(wdir, 'plan.json'), {'dest': {}, 'folders': []})
    app.data.activeHub = hub
    send('progress', {'phase': '現在の状態を確認中', 'done': 0, 'total': 0})
    by_id = {df.id: df for _, df in walk(hub)}
    os.makedirs(out_root, exist_ok=True)
    cur_path = os.path.join(out_root, '_current.txt')
    skip_path = os.path.join(out_root, '_skip.txt')
    # 前回 Fusion ごと落ちたファイルは以後飛ばす
    if os.path.exists(cur_path):
        with open(cur_path, encoding='utf-8') as f:
            crashed = f.read().strip()
        if crashed:
            with open(skip_path, 'a', encoding='utf-8') as f:
                f.write(crashed + '\n')
        os.remove(cur_path)
    skip = set()
    if os.path.exists(skip_path):
        with open(skip_path, encoding='utf-8') as f:
            skip = {x.strip() for x in f if x.strip()}

    used = set()
    done = skipped = failed = other = 0
    log_path = os.path.join(out_root, '_export_log.csv')
    new_log = not os.path.exists(log_path)
    items = inv['items']
    with open(log_path, 'a', newline='', encoding='utf-8-sig') as lf, \
            open(os.path.join(out_root, '_inventory.csv'), 'w', newline='', encoding='utf-8-sig') as invf:
        log = csv.writer(lf)
        if new_log:
            log.writerow(['時刻', '結果', '元の場所', '仕分け先', '名前', '保存先', '備考'])
        invw = csv.writer(invf)
        invw.writerow(['元の場所', '仕分け先', '名前', '拡張子', '版数', '作成日', '最終更新', '保存先'])
        for n, it in enumerate(items, 1):
            adsk.doEvents()
            dest = it['loc'] if layout == 'current' else (plan['dest'].get(it['id'], it['init']) or it['loc'])
            out_dir = os.path.join(out_root, *[safe(x) for x in dest.split('/')])
            base = os.path.join(out_dir, safe(it['name']))
            ext = it['ext'] if it['ext'] else 'bin'
            path, k = f'{base}.{ext}', 2
            while path.lower() in used:
                path, k = f'{base} ({k}).{ext}', k + 1
            used.add(path.lower())
            invw.writerow([it['loc'], dest, it['name'], it['ext'], it['ver'], it['created'], it['modified'], path])
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            os.makedirs(out_dir, exist_ok=True)
            thumb = os.path.join(wdir, 'thumbs', it['thumb'])
            if os.path.exists(thumb) and not os.path.exists(path[:-len(ext)] + 'png'):
                shutil.copyfile(thumb, path[:-len(ext)] + 'png')
            if os.path.exists(path) and os.path.getsize(path) > 0:
                skipped += 1
            elif it['id'] in skip:
                log.writerow([now, '除外(前回落ちた)', it['loc'], dest, it['name'], '', ''])
                failed += 1
            elif it['id'] not in by_id:
                log.writerow([now, '見つからない', it['loc'], dest, it['name'], '', ''])
                failed += 1
            elif it['ext'] != 'f3d':
                try:
                    by_id[it['id']].download(out_dir, None)
                    log.writerow([now, 'その他保存', it['loc'], dest, it['name'], out_dir, ''])
                except Exception as e:
                    log.writerow([now, '未対応', it['loc'], dest, it['name'], '', str(e)[:150]])
                other += 1
            else:
                with open(cur_path, 'w', encoding='utf-8') as f:
                    f.write(it['id'])
                doc = None
                try:
                    doc = app.documents.open(by_id[it['id']], False)
                    design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
                    em = design.exportManager
                    em.execute(em.createFusionArchiveExportOptions(path))
                    log.writerow([now, 'OK', it['loc'], dest, it['name'], path, ''])
                    done += 1
                except Exception as e:
                    log.writerow([now, '失敗', it['loc'], dest, it['name'], path, str(e)[:150]])
                    failed += 1
                finally:
                    if doc:
                        try:
                            doc.close(False)
                        except Exception:
                            pass
                    if os.path.exists(cur_path):
                        os.remove(cur_path)
            if it['ext'] == 'f3d' and os.path.exists(path):
                it['size'] = os.path.getsize(path)
            lf.flush()
            send('progress', {'phase': '書き出し中', 'done': n, 'total': len(items)})
    # 書き出したファイルのサイズで同一のものを探し、一覧に反映する
    same = size_duplicates(items)
    save_json(os.path.join(wdir, 'inventory.json'), inv)
    return {'exported': done, 'skipped': skipped, 'failed': failed, 'other': other, 'sameBySize': same,
            'outDir': out_root.replace('\\', '/')}


# ---------- 画面からの要求 ----------

def handle(action, data, send):
    if action == 'init':
        hubs = app.data.dataHubs
        return {'hubs': [{'id': hubs.item(i).id, 'name': hubs.item(i).name} for i in range(hubs.count)],
                'activeHubId': app.data.activeHub.id if app.data.activeHub else '',
                'workRoot': WORK_ROOT.replace('\\', '/')}
    if action == 'scan':
        return scan(data, send)
    if action == 'pending':
        global PENDING
        PENDING = int(data.get('n', 0))
        return True
    if action == 'savePlan':
        hub = hub_by_id(data['hubId'])
        save_json(os.path.join(work_dir(hub), 'plan.json'), {'dest': data.get('dest', {}), 'folders': data.get('folders', [])})
        return True
    if action == 'preview':
        return preview(data, send)
    if action == 'move':
        return execute_move(data, send)
    if action == 'undo':
        return undo_move(data, send)
    if action == 'export':
        return execute_export(data, send)
    if action == 'pickFolder':
        dlg = ui.createFolderDialog()
        dlg.title = '書き出し先のフォルダ'
        return dlg.folder if dlg.showDialog() == adsk.core.DialogResults.DialogOK else ''
    if action == 'openUrl':
        url = data.get('url', '')
        if url.startswith('https://sin1.studio/'):   # 決まったサイト以外は開かない
            webbrowser.open(url)
        return True
    if action == 'openFolder':
        p = data.get('path', '')
        if p and os.path.exists(p):
            os.startfile(p) if hasattr(os, 'startfile') else None
        return True
    raise RuntimeError('不明な操作: ' + action)
