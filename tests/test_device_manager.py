from __future__ import annotations

from nostr_sdk import Keys

from bitcoin_nostr_chat.signals_min import SignalsMin
from bitcoin_nostr_chat.ui.device_manager import DeviceManager, TrustedDeviceItem, UntrustedDeviceItem
from bitcoin_nostr_chat.ui.ui import UI
from pytestqt.qtbot import QtBot


def test_device_manager_items_are_parented_and_not_top_level_windows(qtbot: QtBot) -> None:
    widget = DeviceManager()
    qtbot.addWidget(widget)

    widget.create_trusted_device(pub_key_bech32="trusted-device")
    widget.create_untrusted_device(pub_key_bech32="untrusted-device")

    trusted_item = widget.trusted.get_device("trusted-device")
    untrusted_item = widget.untrusted.get_device("untrusted-device")

    assert isinstance(trusted_item, TrustedDeviceItem)
    assert isinstance(untrusted_item, UntrustedDeviceItem)

    assert trusted_item.parentWidget() is widget.trusted.viewport()
    assert untrusted_item.parentWidget() is widget.untrusted.viewport()
    assert trusted_item.close_button.parentWidget() is trusted_item
    assert untrusted_item.button_trust.parentWidget() is untrusted_item

    assert not trusted_item.isWindow()
    assert not untrusted_item.isWindow()
    assert not trusted_item.close_button.isWindow()
    assert not untrusted_item.button_trust.isWindow()


def test_nostr_ui_containers_are_parented_and_not_top_level_windows(qtbot: QtBot) -> None:
    widget = UI(my_keys=Keys.generate(), signals_min=SignalsMin())
    qtbot.addWidget(widget)

    assert widget.left_side.parentWidget() is widget.splitter
    assert widget.header.parentWidget() is widget.left_side
    assert widget.toolbar_button.parentWidget() is widget.header
    assert widget.device_manager.parentWidget() is widget.left_side

    assert not widget.left_side.isWindow()
    assert not widget.header.isWindow()
    assert not widget.toolbar_button.isWindow()
    assert not widget.device_manager.isWindow()
