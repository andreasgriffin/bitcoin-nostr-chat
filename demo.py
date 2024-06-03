import logging
from typing import Dict
from uuid import uuid4

from bitcoin_nostr_chat.signals_min import SignalsMin

logging.basicConfig(level=logging.DEBUG)


import argparse
import hashlib
import json

import bdkpython as bdk
from nostr_sdk import Keys, SecretKey
from PyQt6.QtGui import QCloseEvent

from bitcoin_nostr_chat.nostr_sync import NostrSync

logger = logging.getLogger()  # Getting the root logger

import sys

from PyQt6.QtWidgets import QApplication, QMainWindow


def save_dict_to_file(dict_obj: Dict, file_path: str):
    """
    Serialize a dictionary and save it to a file in JSON format.

    Args:
    - dict_obj: The dictionary to be serialized.
    - file_path: The path of the file where the dictionary will be saved.
    """
    try:
        with open(file_path, "w") as json_file:
            json.dump(dict_obj, json_file)
    except IOError as e:
        print(f"Error saving dictionary to {file_path}: {e}")


def load_dict_from_file(file_path: str):
    """
    Load and deserialize a JSON-formatted file into a dictionary.

    Args:
    - file_path: The path of the file to load the dictionary from.

    Returns:
    - The dictionary restored from the file. Returns None if an error occurs.
    """
    try:
        with open(file_path, "r") as json_file:
            return json.load(json_file)
    except IOError as e:
        print(f"Error loading dictionary from {file_path}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {file_path}: {e}")
        return None


class DemoApp(QMainWindow):
    def __init__(self, file_name, signals_min: SignalsMin, protcol_secret_str: str = str(uuid4())):
        super().__init__()
        self.file_name = file_name

        d = load_dict_from_file(file_name)
        if d:
            self.nostr_sync = NostrSync.from_dump(d, network=bdk.Network.REGTEST, signals_min=signals_min)
        else:

            keys = Keys(
                secret_key=SecretKey.from_hex(hashlib.sha256(protcol_secret_str.encode("utf-8")).hexdigest())
            )

            self.nostr_sync = NostrSync.from_keys(
                network=bdk.Network.REGTEST,
                protocol_keys=keys,
                device_keys=Keys.generate(),
                signals_min=signals_min,
            )
        self.nostr_sync.subscribe()
        self.setCentralWidget(self.nostr_sync.gui)
        self.setWindowTitle("Demo App")

    def closeEvent(self, event: QCloseEvent) -> None:
        save_dict_to_file(self.nostr_sync.dump(), self.file_name)
        event.accept()  # Proceed to close the application


def parse_args():

    parser = argparse.ArgumentParser(description="Demo Nostr Chat")
    parser.add_argument(
        "--file_name", help="A filename to store the details in", default="nostr_demo_app.json"
    )
    parser.add_argument(
        "--protcol_secret_str",
        help="A secret for discovering other clients. This is required if there is no previous stored file.",
    )
    parser.add_argument(
        "--profile", action="store_true", help="Enable profiling. Visualize with snakeviz .prof_stats"
    )

    return parser.parse_args()


def main(args):
    app = QApplication(sys.argv)
    demoApp = DemoApp(
        file_name=args.file_name, signals_min=SignalsMin(), protcol_secret_str=args.protcol_secret_str
    )
    demoApp.show()
    app.exec()


if __name__ == "__main__":
    import cProfile
    import os
    from pstats import Stats

    args = parse_args()

    if args.profile:
        with cProfile.Profile() as pr:
            main(args)

        # run in bash "snakeviz .prof_stats &"  to visualize the stats
        with open("profiling_stats.txt", "w") as stream:
            stats = Stats(pr, stream=stream)
            stats.strip_dirs()
            stats.sort_stats("time")
            stats.dump_stats(".prof_stats")
            os.system("snakeviz .prof_stats & ")
            # os.system("pyprof2calltree -i .prof_stats -k & ")
    else:
        main(args)
