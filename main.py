"""Ash & Oath — run me:  python main.py"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def ensure_assets():
    # generated in a subprocess so its SDL dummy-video env var can't leak
    # into this process and hide the game window
    from game.assets import assets_exist
    if not assets_exist():
        print("[boot] generating pixel art...")
        subprocess.run([sys.executable, os.path.join(ROOT, "assets", "generate_assets.py")],
                       check=True)


def main():
    ensure_assets()
    from game.engine import Game
    Game().run()


if __name__ == "__main__":
    main()
