import argparse
import hashlib
import json
import logging
import sys
from uuid import uuid4

import bdkpython as bdk
from nostr_sdk import Keys, SecretKey
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow

from bitcoin_nostr_chat import DEFAULT_USE_COMPRESSION
from bitcoin_nostr_chat.nostr_sync import NostrSyncWithSingleChats
from bitcoin_nostr_chat.signals_min import SignalsMin

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)  # Getting the root logger


def save_dict_to_file(dict_obj: dict, file_path: str):
    """
    Serialize a dictionary and save it to a file in JSON format.

    Args:
    - dict_obj: The dictionary to be serialized.
    - file_path: The path of the file where the dictionary will be saved.
    """
    try:
        with open(file_path, "w") as json_file:
            json.dump(dict_obj, json_file)
    except OSError as e:
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
        with open(file_path) as json_file:
            return json.load(json_file)
    except OSError as e:
        print(f"Error loading dictionary from {file_path}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {file_path}: {e}")
        return None


class DemoApp(QMainWindow):
    def __init__(
        self,
        file_name,
        signals_min: SignalsMin,
        protcol_secret_str: str = str(uuid4()),
        use_compression=DEFAULT_USE_COMPRESSION,
    ):
        super().__init__()
        self.file_name = file_name

        d = load_dict_from_file(file_name)
        if d:
            self.nostr_sync = NostrSyncWithSingleChats.from_dump(
                d, signals_min=signals_min, loop_in_thread=None
            )
        else:
            keys = Keys(
                secret_key=SecretKey.parse(hashlib.sha256(protcol_secret_str.encode("utf-8")).hexdigest())
            )

            self.nostr_sync = NostrSyncWithSingleChats.from_keys(
                network=bdk.Network.REGTEST,
                protocol_keys=keys,
                device_keys=Keys.generate(),
                signals_min=signals_min,
                use_compression=use_compression,
                loop_in_thread=None,
            )
        self.nostr_sync.subscribe()
        self.setCentralWidget(self.nostr_sync.ui)
        self.setWindowTitle("Demo App")

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        save_dict_to_file(self.nostr_sync.dump(), self.file_name)
        self.nostr_sync.close()
        super().closeEvent(a0)


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
        "--disable_compression",
        action="store_true",
        help="Disables the compression that is usually used to reduce load on relays",
    )
    parser.add_argument(
        "--profile", action="store_true", help="Enable profiling. Visualize with snakeviz .prof_stats"
    )

    return parser.parse_args()


def main(args):
    app = QApplication(sys.argv)
    demoApp = DemoApp(
        file_name=args.file_name,
        signals_min=SignalsMin(),
        protcol_secret_str=args.protcol_secret_str,
        use_compression=not args.disable_compression,
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
