# ThumbSorter: ツールバー「ユーティリティ > アドイン」にボタンを置き、仕分け用のパネルを開く。
# 画面(palette/index.html)と処理(sorter_core.py)のやり取りはここで中継する。

import adsk.core
import importlib
import json
import os
import traceback

from . import sorter_core as core
importlib.reload(core)   # アドインを停止→実行し直したときに sorter_core の変更も読み込む

CMD_ID = 'FusionSorter_open'
PALETTE_ID = 'FusionSorter_palette'
PANEL_ID = 'SolidScriptsAddinsPanel'
HERE = os.path.dirname(os.path.abspath(__file__))

app = None
ui = None
handlers = []   # イベントハンドラーはGCされないよう保持する


def palette():
    return ui.palettes.itemById(PALETTE_ID)


def send(action, data):
    p = palette()
    if p:
        p.sendInfoToHTML(action, json.dumps(data, ensure_ascii=False))
        adsk.doEvents()


class HTMLHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        args = adsk.core.HTMLEventArgs.cast(args)
        if args.action in ('response', ''):
            return
        try:
            data = json.loads(args.data) if args.data else {}
            result = core.handle(args.action, data, send)
            args.returnData = json.dumps({'ok': True, 'result': result}, ensure_ascii=False)
        except Exception as e:
            args.returnData = json.dumps({'ok': False, 'error': str(e), 'trace': traceback.format_exc()}, ensure_ascii=False)


class ClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def notify(self, args):
        pass


class OpenHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            p = palette()
            if not p:
                url = os.path.join(HERE, 'palette', 'index.html').replace('\\', '/')
                p = ui.palettes.add(PALETTE_ID, 'ThumbSorter', url, True, True, True, 1280, 820, True)
                p.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
                h = HTMLHandler()
                p.incomingFromHTML.add(h)
                handlers.append(h)
                c = ClosedHandler()
                p.closed.add(c)
                handlers.append(c)
            p.isVisible = True
        except Exception:
            ui.messageBox('ThumbSorterを開けませんでした:\n' + traceback.format_exc())


def run(context):
    global app, ui
    app = adsk.core.Application.get()
    ui = app.userInterface
    core.init(app, ui)
    try:
        cmd = ui.commandDefinitions.itemById(CMD_ID)
        if cmd:
            cmd.deleteMe()   # アイコンや名前の変更を反映するため作り直す
        cmd = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, 'ThumbSorter', 'ハブのデザインをサムネイルを見ながら仕分けて、移動または書き出しする',
            os.path.join(HERE, 'resources', 'icon'))
        h = OpenHandler()
        cmd.commandCreated.add(h)
        handlers.append(h)
        panel = ui.allToolbarPanels.itemById(PANEL_ID)
        if panel:
            ctrl = panel.controls.itemById(CMD_ID) or panel.controls.addCommand(cmd)
            # ▼メニューに隠れず、パネルに直接ボタンを出す
            ctrl.isPromoted = True
            ctrl.isPromotedByDefault = True
    except Exception:
        ui.messageBox('ThumbSorterの起動に失敗しました:\n' + traceback.format_exc())


def stop(context):
    try:
        panel = ui.allToolbarPanels.itemById(PANEL_ID)
        ctrl = panel.controls.itemById(CMD_ID) if panel else None
        if ctrl:
            ctrl.deleteMe()
        cmd = ui.commandDefinitions.itemById(CMD_ID)
        if cmd:
            cmd.deleteMe()
        p = palette()
        if p:
            p.deleteMe()
    except Exception:
        pass
