"""Run from the repository's virtual environment; serves on loopback only."""
import argparse
import threading
import webbrowser
import uvicorn


class BrowserServer(uvicorn.Server):
    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        if self.started:
            url = f"http://{self.config.host}:{self.config.port}"
            threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="Open the app in your browser")
    args = parser.parse_args()
    config = uvicorn.Config("rutile3.api.app:app", host="127.0.0.1", port=args.port)
    server_class = BrowserServer if args.open else uvicorn.Server
    server_class(config).run()
