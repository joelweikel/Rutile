"""Run from the repository's virtual environment; serves on loopback only."""
import argparse
import threading
import webbrowser
import uvicorn


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="Open the app in your browser")
    args = parser.parse_args()
    if args.open:
        threading.Timer(2, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    uvicorn.run("rutile3.api.app:app", host="127.0.0.1", port=args.port)
