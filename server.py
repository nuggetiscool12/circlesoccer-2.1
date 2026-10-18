import os, json, secrets, string, asyncio
from pathlib import Path
from aiohttp import web, WSMsgType

BASE = Path(__file__).resolve().parent
rooms = {}
ALPHABET = string.ascii_uppercase + string.digits

async def index(request):
    return web.FileResponse(BASE / 'index.html')

async def socket(request):
    ws = web.WebSocketResponse(max_msg_size=2_000_000, heartbeat=30)
    await ws.prepare(request)
    room = role = None
    try:
        async for event in ws:
            if event.type != WSMsgType.TEXT:
                continue
            try:
                msg = json.loads(event.data)
            except (ValueError, TypeError):
                continue
            if not isinstance(msg, dict):
                continue
            kind = msg.get('type')
            if kind == 'create':
                if room:
                    continue
                code = ''.join(secrets.choice(ALPHABET) for _ in range(6))
                while code in rooms:
                    code = ''.join(secrets.choice(ALPHABET) for _ in range(6))
                rooms[code] = {'host': ws, 'guest': None}
                room, role = code, 'host'
                await ws.send_json({'type':'created','code':code,'role':'host'})
            elif kind == 'join':
                if room:
                    continue
                code = str(msg.get('code','')).upper().strip()
                r = rooms.get(code)
                if not r or r['guest'] is not None or r['host'].closed:
                    await ws.send_json({'type':'error','message':'Room unavailable. Check the code and try again.'})
                    continue
                room, role = code, 'guest'
                r['guest'] = ws
                await ws.send_json({'type':'joined','code':code,'role':'guest'})
                await r['host'].send_json({'type':'peer','connected':True})
            elif room and room in rooms:
                r = rooms[room]
                target = r['guest'] if role == 'host' and kind == 'state' else r['host'] if role == 'guest' and kind == 'input' else None
                if target and not target.closed:
                    await target.send_str(event.data)
    finally:
        if room in rooms:
            r = rooms[room]
            if role == 'host' and r['host'] is ws:
                if r['guest'] and not r['guest'].closed:
                    await r['guest'].send_json({'type':'error','message':'Host disconnected. Create a new room.'})
                del rooms[room]
            elif role == 'guest' and r['guest'] is ws:
                r['guest'] = None
                if not r['host'].closed:
                    await r['host'].send_json({'type':'peer','connected':False})
    return ws

app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/logo.png', lambda req: web.FileResponse(BASE / 'logo.png'))
app.router.add_get('/favicon.png', lambda req: web.FileResponse(BASE / 'favicon.png'))
app.router.add_get('/ws', socket)
app.router.add_get('/health', lambda req: web.Response(text='OK'))

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=int(os.environ.get('PORT', '8000')))
