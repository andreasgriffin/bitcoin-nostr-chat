from __future__ import annotations

from collections import deque
from datetime import datetime

import bdkpython as bdk
from bitcoin_qr_tools.data import DataType
from nostr_sdk import EventId, Keys
from PyQt6.QtCore import QObject, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QImage
from pytestqt.qtbot import QtBot
from bitcoin_nostr_chat.base_dm import BaseDM

from bitcoin_nostr_chat.chat import CONFIRMED_ICON_NAME, PENDING_ICON_NAME, Chat
from bitcoin_nostr_chat.chat_dm import ChatDM, ChatLabel
from bitcoin_nostr_chat.signals_min import SignalsMin
from bitcoin_nostr_chat.ui.chat_component import ChatItemDelegate
from bitcoin_nostr_chat.ui.util import svg_tools


class FakeNotificationHandler:
    def __init__(self):
        self.processed_dms: deque[BaseDM] = deque()


class FakeAsyncDmConnection:
    def __init__(self):
        self.notification_handler = FakeNotificationHandler()


class FakeDmConnection:
    def __init__(self):
        self.async_dm_connection = FakeAsyncDmConnection()


class FakeGroupChat(QObject):
    signal_dm = pyqtSignal(ChatDM)

    def __init__(self, my_keys: Keys, members: list[Keys] | None = None):
        super().__init__()
        self._my_keys = my_keys
        self.members = [member.public_key() for member in (members or [])]
        self.aliases: dict[str, str] = {}
        self.use_compression = True
        self.dm_connection = FakeDmConnection()
        self.pending_publish_callback = None
        self.pending_self_callback = None

    def my_public_key(self):
        return self._my_keys.public_key()

    def send(
        self,
        dm: ChatDM,
        send_also_to_me=True,
        on_publish_result=None,
        on_self_published=None,
    ):
        self.send_to(
            dm=dm,
            recipients=self.members,
            send_also_to_me=send_also_to_me,
            on_publish_result=on_publish_result,
            on_self_published=on_self_published,
        )

    def send_to(
        self,
        dm: ChatDM,
        recipients,
        send_also_to_me=True,
        on_publish_result=None,
        on_self_published=None,
    ):
        self.pending_publish_callback = on_publish_result
        self.pending_self_callback = on_self_published

    def publish_result(self, recipient_bech32: str, event_id: EventId | Exception | None):
        if self.pending_publish_callback:
            self.pending_publish_callback(recipient_bech32, event_id)  # type: ignore

    def self_publish_result(self, event_id: EventId | Exception | None):
        if self.pending_self_callback:
            self.pending_self_callback(event_id)  # type: ignore


class FakeData:
    def __init__(self, text: str):
        self.text = text
        self.data_type = DataType.PSBT
        self.data = text

    def data_as_string(self) -> str:
        return self.text


def icon_bytes(icon: QIcon) -> bytes:
    image = icon.pixmap(16, 16).toImage().convertToFormat(QImage.Format.Format_ARGB32)
    return image.bits().asstring(image.sizeInBytes())  # type: ignore


def make_self_copy(dm: ChatDM, my_keys: Keys) -> ChatDM:
    return ChatDM(
        label=dm.label,
        created_at=dm.created_at,
        description=dm.description,
        data=dm.data,
        intended_recipient=dm.intended_recipient,
        author=my_keys.public_key(),
        event=None,
        use_compression=dm.use_compression,
    )


def make_chat(qtbot: QtBot, member_count: int = 1) -> tuple[Chat, FakeGroupChat, Keys]:
    my_keys = Keys.generate()
    member_keys = [Keys.generate() for _ in range(member_count)]
    group_chat = FakeGroupChat(my_keys=my_keys, members=member_keys)
    chat = Chat(network=bdk.Network.REGTEST, group_chat=group_chat, signals_min=SignalsMin())  # type: ignore
    qtbot.addWidget(chat.gui)
    return chat, group_chat, my_keys


def get_first_item(chat: Chat):
    return chat.gui.chat_component.list_widget.item(0)


def test_outgoing_text_message_appears_immediately_with_pending_icon(qtbot: QtBot) -> None:
    chat, _, _ = make_chat(qtbot)

    chat.on_send_message_in_groupchat("hello")

    item = get_first_item(chat)
    assert chat.gui.chat_component.list_widget.count() == 1
    assert item.text() == "Me: hello"  # type: ignore
    assert "Pending" in item.toolTip()  # type: ignore
    assert icon_bytes(item.icon()) == icon_bytes(svg_tools.get_QIcon(PENDING_ICON_NAME))  # type: ignore


def test_self_copy_updates_existing_row_without_duplicate(qtbot: QtBot) -> None:
    chat, group_chat, my_keys = make_chat(qtbot)

    chat.on_send_message_in_groupchat("hello")
    optimistic_dm = chat.gui.dms[0]
    group_chat.signal_dm.emit(make_self_copy(optimistic_dm, my_keys))

    assert chat.gui.chat_component.list_widget.count() == 1
    assert chat.gui.dms[0].author == my_keys.public_key()


def test_confirmation_requires_remote_publish_and_self_copy(qtbot: QtBot) -> None:
    chat, group_chat, my_keys = make_chat(qtbot)

    chat.on_send_message_in_groupchat("hello")
    optimistic_dm = chat.gui.dms[0]
    item = get_first_item(chat)
    recipient = group_chat.members[0].to_bech32()

    group_chat.signal_dm.emit(make_self_copy(optimistic_dm, my_keys))

    assert "Pending" in item.toolTip()  # type: ignore
    assert icon_bytes(item.icon()) == icon_bytes(svg_tools.get_QIcon(PENDING_ICON_NAME))  # type: ignore

    group_chat.publish_result(recipient, EventId.parse("0" * 64))

    assert "Published" in item.toolTip()  # type: ignore
    assert icon_bytes(item.icon()) == icon_bytes(svg_tools.get_QIcon(CONFIRMED_ICON_NAME))  # type: ignore


def test_failed_remote_publish_stays_pending(qtbot: QtBot) -> None:
    chat, group_chat, my_keys = make_chat(qtbot)

    chat.on_send_message_in_groupchat("hello")
    optimistic_dm = chat.gui.dms[0]
    item = get_first_item(chat)

    group_chat.signal_dm.emit(make_self_copy(optimistic_dm, my_keys))
    group_chat.publish_result(group_chat.members[0].to_bech32(), None)

    assert "Failed" in item.toolTip()  # type: ignore
    assert icon_bytes(item.icon()) == icon_bytes(svg_tools.get_QIcon(PENDING_ICON_NAME))  # type: ignore


def test_exception_publish_result_stays_pending(qtbot: QtBot) -> None:
    chat, group_chat, my_keys = make_chat(qtbot)

    chat.on_send_message_in_groupchat("hello")
    optimistic_dm = chat.gui.dms[0]
    item = get_first_item(chat)

    group_chat.signal_dm.emit(make_self_copy(optimistic_dm, my_keys))
    group_chat.publish_result(group_chat.members[0].to_bech32(), RuntimeError("relay offline"))

    assert "relay offline" in item.toolTip()  # type: ignore
    assert icon_bytes(item.icon()) == icon_bytes(svg_tools.get_QIcon(PENDING_ICON_NAME))  # type: ignore
    assert len(chat._outgoing_delivery_states) == 1


def test_clear_all_discards_pending_outgoing_state(qtbot: QtBot) -> None:
    chat, group_chat, _ = make_chat(qtbot)

    chat.on_send_message_in_groupchat("hello")
    chat.gui.chat_component.list_widget.clear()
    chat.gui.chat_component.list_widget.signal_clear.emit()
    group_chat.publish_result(group_chat.members[0].to_bech32(), EventId.parse("0" * 64))

    assert chat.gui.chat_component.list_widget.count() == 0
    assert not chat._outgoing_delivery_states
    assert not chat.gui._local_id_to_item


def test_outgoing_file_message_uses_same_status_flow(qtbot: QtBot) -> None:
    chat, group_chat, my_keys = make_chat(qtbot, member_count=0)
    file_dm = ChatDM(
        label=ChatLabel.GroupChat,
        created_at=datetime.now(),
        description="demo.psbt",
        data=FakeData("psbt-data"),  # type: ignore
        use_compression=group_chat.use_compression,
    )

    chat._send_chat_dm(file_dm)
    item = get_first_item(chat)

    assert chat.gui.chat_component.list_widget.count() == 1
    assert "Pending" in item.toolTip()  # type: ignore
    assert icon_bytes(item.icon()) == icon_bytes(svg_tools.get_QIcon(PENDING_ICON_NAME))  # type: ignore

    group_chat.signal_dm.emit(make_self_copy(file_dm, my_keys))

    assert "Published" in item.toolTip()  # type: ignore
    assert icon_bytes(item.icon()) == icon_bytes(svg_tools.get_QIcon(CONFIRMED_ICON_NAME))  # type: ignore


def test_right_aligned_icon_rect_uses_content_rect_for_vertical_centering() -> None:
    text_rect = QRect(120, 4, 60, 12)
    content_rect = QRect(0, 0, 200, 24)
    icon_rect = ChatItemDelegate.right_aligned_icon_rect(text_rect, content_rect, QSize(12, 12))

    assert icon_rect.left() == 102
    assert icon_rect.top() == 6


def test_vertically_centered_alignment_preserves_horizontal_alignment() -> None:
    alignment = ChatItemDelegate.vertically_centered_alignment(Qt.AlignmentFlag.AlignRight)

    assert alignment & Qt.AlignmentFlag.AlignRight
    assert alignment & Qt.AlignmentFlag.AlignVCenter
