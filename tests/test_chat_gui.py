from __future__ import annotations

from bitcoin_nostr_chat.signals_min import SignalsMin
from bitcoin_nostr_chat.ui.chat_gui import ChatGui
from pytestqt.qtbot import QtBot


def test_chat_gui_controls_are_parented_and_not_top_level_windows(qtbot: QtBot) -> None:
    widget = ChatGui(signals_min=SignalsMin())
    qtbot.addWidget(widget)

    assert widget.textInput.parentWidget() is widget.controls_widget
    assert widget.sendButton.parentWidget() is widget.controls_widget
    assert widget.shareButton.parentWidget() is widget.controls_widget

    assert not widget.textInput.isWindow()
    assert not widget.sendButton.isWindow()
    assert not widget.shareButton.isWindow()
