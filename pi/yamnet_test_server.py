"""Serve only the phone microphone/YAMNet test, without vision, STT or motor hardware."""
import argparse
from pathlib import Path
import ssl

from aiohttp import web

from yamnet_stream import YAMNetSocket

ROOT = Path(__file__).resolve().parent.parent


def make_app():
    app = web.Application()
    classifier = YAMNetSocket()

    async def index(request):
        return web.FileResponse(ROOT / 'web' / 'sound-test.html',
                                headers={'Cache-Control': 'no-store'})

    async def client_log(request):
        message = (await request.text())[:1000].replace('\n', ' ')
        print(f'[phone] {message}', flush=True)
        return web.Response(status=204)

    app.router.add_get('/', index)
    app.router.add_get('/sound-ws', classifier.handle)
    app.router.add_post('/client-log', client_log)
    app.router.add_static('/', ROOT / 'web')
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8444)
    parser.add_argument('--cert', type=Path, default=ROOT / 'certs' / 'cert.pem')
    parser.add_argument('--key', type=Path, default=ROOT / 'certs' / 'key.pem')
    args = parser.parse_args()
    if not args.cert.is_file() or not args.key.is_file():
        parser.error('TLS certificate missing. Run sh scripts/make_cert.sh in this test copy first.')
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(args.cert, args.key)
    print(f'Phone: https://<JETSON_IP>:{args.port}/', flush=True)
    print('YAMNet only: no camera, caption service, or motor connection.', flush=True)
    web.run_app(make_app(), port=args.port, ssl_context=tls)


if __name__ == '__main__':
    main()
