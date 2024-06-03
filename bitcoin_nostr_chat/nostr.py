#
# Nostr Sync
# Copyright (C) 2024 Andreas Griffin
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of version 3 of the GNU General Public License as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see https://www.gnu.org/licenses/gpl-3.0.html
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import json
import logging
from abc import abstractmethod
from datetime import datetime, timedelta
from time import sleep

logger = logging.getLogger(__name__)


import base64
import enum
import zlib
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

import bdkpython as bdk
import cbor2
import requests
from bitcoin_qrreader.bitcoin_qr import Data, DataType
from nostr_sdk import (
    Client,
    Event,
    EventId,
    Filter,
    HandleNotification,
    Keys,
    Kind,
    KindEnum,
    NostrSigner,
    PublicKey,
    Relay,
    RelayMessage,
    RelayStatus,
    SecretKey,
    Timestamp,
    nip04_decrypt,
)
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


def fetch_and_parse_json(url: str) -> Optional[Any]:
    """
    Fetches data from the given URL and parses it as JSON.

    Args:
    url (str): The URL to fetch the data from.

    Returns:
    dict or None: Parsed JSON data if successful, None otherwise.
    """
    try:
        logger.debug(f"fetch_and_parse_json requests.get({url})")
        response = requests.get(url, timeout=2)
        response.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code
        return response.json()
    except requests.RequestException as e:
        logger.error(f"An error occurred: {e}")
        return None


def get_recipient_public_key(event: Event) -> Optional[PublicKey]:
    if not event.kind().match_enum(KindEnum.ENCRYPTED_DIRECT_MESSAGE()):
        return None
    for tag in event.tags():
        tag_enum = tag.as_enum()
        if tag_enum.is_public_key_tag():
            recipient_public_key: PublicKey = tag_enum.public_key
            return recipient_public_key
    return None


@dataclass
class RelayList:
    relays: List[str]
    last_updated: datetime
    max_age: Optional[int] = 30  # days,  "None" means it is disabled

    @classmethod
    def from_internet(cls) -> "RelayList":
        return RelayList(relays=cls.get_relays(), last_updated=datetime.now())

    @classmethod
    def from_text(cls, text: str, max_age=None) -> "RelayList":
        text = text.replace('"', "").replace(",", "")
        relays = [line.strip() for line in text.strip().split("\n")]
        relays = [line for line in relays if line]
        return RelayList(relays=relays, last_updated=datetime.now(), max_age=max_age)

    def get_subset(self, size: int) -> List[str]:
        return self.relays[: min(len(self.relays), size)]

    def dump(self) -> Dict:
        d = self.__dict__.copy()
        d["last_updated"] = self.last_updated.timestamp()
        return d

    @classmethod
    def from_dump(cls, d: Dict) -> "RelayList":
        d["last_updated"] = datetime.fromtimestamp(d["last_updated"])
        return cls(**d)

    def update_relays(self):
        self.relays = self.get_relays()
        self.last_updated = datetime.now()

    def is_stale(self) -> bool:
        if not self.max_age:
            return False
        return self.last_updated < datetime.now() - timedelta(days=self.max_age)

    def update_if_stale(self):
        if self.is_stale():
            self.update_relays()

    @classmethod
    def preferred_relays(cls) -> List[str]:
        return [
            "wss://relay1.nostrchat.io",
            "wss://relay.nostrati.com",
            "wss://relay.minibits.cash",
            "wss://us.nostr.wine",
            "wss://nostr.koning-degraaf.nl",
            "wss://nostr.mom",
        ]

    @classmethod
    def default_delays(cls) -> List[str]:
        return [
            "wss://relay.damus.io",
            "wss://nostr.mom",
            "wss://nostr.slothy.win",
            "wss://nos.lol",
            "wss://nostr.massmux.com",
            "wss://nostr-relay.schnitzel.world",
            "wss://knostr.neutrine.com",
            "wss://nostr.vulpem.com",
            "wss://relay.nostr.com.au",
            "wss://e.nos.lol",
            "wss://relay.orangepill.dev",
            "wss://nostr.data.haus",
            "wss://nostr.koning-degraaf.nl",
            "wss://nostr-relay.texashedge.xyz",
            "wss://nostr.wine",
            "wss://nostr-1.nbo.angani.co",
            "wss://nostr.easydns.ca",
            "wss://nostr.cheeserobot.org",
            "wss://nostr.inosta.cc",
            "wss://relay.nostrview.com",
            "wss://relay.nostromo.social",
            "wss://arc1.arcadelabs.co",
            "wss://nostr.zkid.social",
            "wss://bitcoinmaximalists.online",
            "wss://private.red.gb.net",
            "wss://nostr21.com",
            "wss://offchain.pub",
            "wss://relay.nostrcheck.me",
            "wss://relay.nostr.vet",
            "wss://relay.hamnet.io",
            "wss://jp-relay-nostr.invr.chat",
            "wss://relay.nostr.wirednet.jp",
            "wss://nostrelay.yeghro.site",
            "wss://nostr.topeth.info",
            "wss://relay.nostrati.com",
            "wss://nostr.danvergara.com",
            "wss://nostr.roundrockbitcoiners.com",
            "wss://nostr.shawnyeager.net",
            "wss://relay.orange-crush.com",
            "wss://nostr.bitcoiner.social",
            "wss://relay.snort.social",
            "wss://nostr.bch.ninja",
            "wss://relay.nostriches.org",
            "wss://atlas.nostr.land",
            "wss://brb.io",
            "wss://relay.roli.social",
            "wss://global-relay.cesc.trade",
            "wss://relay.reeve.cn",
            "wss://relay.nostrid.com",
            "wss://nostr.noones.com",
            "wss://relay.nostr.nu",
            "wss://eden.nostr.land",
            "wss://nostr.sebastix.dev",
            "wss://nostr.fmt.wiz.biz",
            "wss://nostr.ownbtc.online",
            "wss://nostr.bitcoinplebs.de",
            "wss://tmp-relay.cesc.trade",
            "wss://bitcoiner.social",
            "wss://nostr.easify.de",
            "wss://xmr.usenostr.org",
            "wss://nostr-relay.nokotaro.com",
            "wss://nostr.naut.social",
            "wss://nostrsatva.net",
            "wss://at.nostrworks.com",
            "wss://nostr01.vida.dev",
            "wss://nostr.sovbit.host",
            "wss://nostr.plebchain.org",
            "wss://relay.nostr.bg",
            "wss://nostr.primz.org",
            "wss://relay.nostrified.org",
            "wss://nostr.decentony.com",
            "wss://relay.primal.net",
            "wss://nostr.orangepill.dev",
            "wss://puravida.nostr.land",
            "wss://nostr.1sat.org",
            "wss://nostr.oxtr.dev",
            "wss://nostr-relay.derekross.me",
            "wss://relay.s3x.social",
            "wss://nostrrelay.com",
            "wss://nostr-pub.semisol.dev",
            "wss://nostr.semisol.dev",
            "wss://relay.nostr.wf",
            "wss://nostr.land",
            "wss://relay.mostr.pub",
            "wss://relay.nostrplebs.com",
            "wss://purplepag.es",
            "wss://paid.nostrified.org",
            "wss://relayable.org",
            "wss://btc-italia.online",
            "wss://yestr.me",
            "wss://relay.nostr.sc",
            "wss://nostr.portemonero.com",
            "wss://adult.18plus.social",
            "wss://nostr.zbd.gg",
            "wss://ca.orangepill.dev",
            "wss://nostr-02.dorafactory.org",
            "wss://relay.chicagoplebs.com",
            "wss://relay.hodl.ar",
            "wss://therelayofallrelays.nostr1.com",
            "wss://nostr.carlostkd.ch",
            "wss://rly.nostrkid.com",
            "wss://welcome.nostr.wine",
            "wss://nostr.maximacitadel.org",
            "wss://nostr-relay.app",
            "wss://ithurtswhenip.ee",
            "wss://stealth.wine",
            "wss://nostr.thesamecat.io",
            "wss://nostr.zenon.info",
            "wss://yabu.me",
            "wss://relay.deezy.io",
            "wss://nrelay.c-stellar.net",
            "wss://africa.nostr.joburg",
            "wss://nostrja-kari.heguro.com",
            "wss://paid.nostr.lc",
            "wss://nostr.ingwie.me",
            "wss://relay2.nostrchat.io",
            "wss://ln.weedstr.net/nostrrelay/weedstr",
            "wss://relay1.nostrchat.io",
            "wss://nostr2.sanhauf.com",
            "wss://nostr.otc.sh",
            "wss://freerelay.xyz",
            "wss://nostrua.com",
            "wss://relay.devstr.org",
            "wss://nostr.dakukitsune.ca",
            "wss://relay2.nostr.vet",
            "wss://nostr.debancariser.com",
            "wss://nostrpub.yeghro.site",
            "wss://nostr.schorsch.fans",
            "wss://ca.relayable.org",
            "wss://nostr.hexhex.online",
            "wss://nostr.reelnetwork.eu",
            "wss://relay.nostr.directory",
            "wss://booger.pro",
            "wss://relay.stpaulinternet.net",
            "wss://nostr.donky.social",
            "wss://nostr.438b.net",
            "wss://nostr.impervious.live",
            "wss://nostr.bolt.fun",
            "wss://nostr.btc-library.com",
            "wss://sats.lnaddy.com/nostrclient/api/v1/relay",
            "wss://relay.mutinywallet.com",
            "wss://nostr.sagaciousd.com",
            "wss://nostrools.nostr1.com",
            "wss://nostrja-world-relays-test.heguro.com",
            "wss://ryan.nostr1.com",
            "wss://satdow.relaying.io",
            "wss://relay.bitcoinpark.com",
            "wss://la.relayable.org",
            "wss://nostr-01.yakihonne.com",
            "wss://nostr.fort-btc.club",
            "wss://test.relay.report",
            "wss://relay.nostrcn.com",
            "wss://nostr.sathoarder.com",
            "wss://christpill.nostr1.com",
            "wss://relap.orzv.workers.dev",
            "wss://nostr.sixteensixtyone.com",
            "wss://relay.danvergara.com",
            "wss://nostr.heliodex.cf",
            "wss://wbc.nostr1.com",
            "wss://filter.stealth.wine?broadcast=true",
            "wss://lnbits.michaelantonfischer.com/nostrrelay/michaelantonf",
            "wss://pater.nostr1.com",
            "wss://lnbits.eldamar.icu/nostrrelay/relay",
            "wss://butcher.nostr1.com",
            "wss://tictac.nostr1.com",
            "wss://relay.relayable.org",
            "wss://relay.hrf.org",
            "wss://fiatdenier.nostr1.com",
            "wss://relay.ingwie.me",
            "wss://nostr.codingarena.de",
            "wss://fistfistrelay.nostr1.com",
            "wss://au.relayable.org",
            "wss://relay.kamp.site",
            "wss://nostr.stakey.net",
            "wss://a.nos.lol",
            "wss://eu.purplerelay.com",
            "wss://relay.nostrassets.com",
            "wss://hodlbod.nostr1.com",
            "wss://nostr-relay.psfoundation.info",
            "wss://nostr.fractalized.net",
            "wss://21ideas.nostr1.com",
            "wss://hotrightnow.nostr1.com",
            "wss://verbiricha.nostr1.com",
            "wss://rly.bopln.com",
            "wss://teemie1-relay.duckdns.org",
            "wss://relay.ohbe.me",
            "wss://relay.nquiz.io",
            "wss://zh.nostr1.com",
            "wss://bevo.nostr1.com",
            "wss://gardn.nostr1.com",
            "wss://feedstr.nostr1.com",
            "wss://supertestnet.nostr1.com",
            "wss://relay-jp.shino3.net",
            "wss://sakhalin.nostr1.com",
            "wss://adre.su",
            "wss://nostr.kungfu-g.rip",
            "wss://pay21.nostr1.com",
            "wss://testrelay.nostr1.com",
            "wss://nostr-dev.zbd.gg",
            "wss://za.purplerelay.com",
            "wss://in.purplerelay.com",
            "wss://nostr.openordex.org",
            "wss://relay.cxcore.net",
            "wss://vitor.relaying.io",
            "wss://agora.nostr1.com",
            "wss://nostr.hashi.sbs",
            "wss://nostr.lbdev.fun",
            "wss://relay.crimsonleaf363.com",
            "wss://pablof7z.nostr1.com",
            "wss://zyro.nostr1.com",
            "wss://relay.satoshidnc.com",
            "wss://strfry.nostr.lighting",
            "wss://frens.nostr1.com",
            "wss://vitor.nostr1.com",
            "wss://chefstr.nostr1.com",
            "wss://relay.siamstr.com",
            "wss://ae.purplerelay.com",
            "wss://umami.nostr1.com",
            "wss://prism.nostr1.com",
            "wss://sfr0.nostr1.com",
            "wss://n.ok0.org",
            "wss://relay.nostr.wien",
            "wss://relay.nostr.pt",
            "wss://relay.piazza.today",
            "wss://relay.exit.pub",
            "wss://testnet.plebnet.dev/nostrrelay/1",
            "wss://studio314.nostr1.com",
            "wss://ch.purplerelay.com",
            "wss://legend.lnbits.com/nostrclient/api/v1/relay",
            "wss://us.nostr.land",
            "wss://fl.purplerelay.com",
            "wss://relay.minibits.cash",
            "wss://us.nostr.wine",
            "wss://frjosh.nostr1.com",
            "wss://cellar.nostr.wine",
            "wss://inbox.nostr.wine",
            "wss://nostr.hubmaker.io",
            "wss://shawn.nostr1.com",
            "wss://relay.gems.xyz",
            "wss://nostr-02.yakihonne.com",
            "wss://obiurgator.thewhall.com",
            "wss://relay.nos.social",
            "wss://nostr.psychoet.nexus",
            "wss://nostr.1661.io",
            "wss://nostr.tavux.tech",
            "wss://lnbits.aruku.kro.kr/nostrrelay/private",
            "wss://relay.artx.market",
            "wss://lnbits.btconsulting.nl/nostrrelay/nostr",
            "wss://nostr-03.dorafactory.org",
            "wss://nostr.atlbitlab.com",
            "wss://nostr.zoel.network",
            "wss://lnbits.papersats.io/nostrclient/api/v1/relay",
            "wss://yondar.nostr1.com",
            "wss://creatr.nostr.wine",
            "wss://riray.nostr1.com",
            "wss://nostr.pklhome.net",
            "wss://relay.tunestr.io",
            "wss://ren.nostr1.com",
            "wss://theforest.nostr1.com",
            "wss://nostrdevs.nostr1.com",
            "wss://nostr.cahlen.org",
            "wss://nostr.papanode.com",
            "wss://milwaukie.nostr1.com",
            "wss://strfry.chatbett.de",
            "wss://relay.bitmapstr.io",
            "wss://directory.yabu.me",
            "wss://nostr.reckless.dev",
            "wss://srtrelay.c-stellar.net",
            "wss://nostr.lopp.social",
            "wss://vanderwarker.dev/nostrclient/api/v1/relay",
            "wss://relay.notoshi.win",
            "wss://lnbits.satoshibox.io/nostrclient/api/v1/relay",
            "wss://relay.zhoushen929.com",
            "wss://relay.moinsen.com",
            "wss://hayloo88.nostr1.com",
            "wss://140.f7z.io",
            "wss://jumpy-bamboo-euhyboma.scarab.im",
            "wss://beijing.scarab.im",
            "wss://mnl.v0l.io",
            "wss://staging.yabu.me",
            "wss://nostr.notribe.net",
            "wss://rnostr.onrender.com",
            "wss://nostr.ra-willi.com",
            "wss://relay.swisslightning.net",
            "wss://xxmmrr.shogatsu.ovh",
            "wss://relay.agorist.space",
            "wss://relay.lightningassets.art",
            "wss://dev-relay.nostrassets.com",
            "wss://nostr.jfischer.org",
            "wss://frogathon.nostr1.com",
            "wss://marmot.nostr1.com",
            "wss://island.nostr1.com",
            "wss://relay.angor.io",
            "wss://relay.earthly.land",
            "wss://jmoose.rocks",
            "wss://test2.relay.report",
            "wss://relay.strfront.com",
            "wss://relay01.karma.svaha-chain.online",
            "wss://nostr.cyberveins.eu",
            "wss://relay.nostr.net",
            "wss://beta.1661.io",
            "wss://nostr.8k-lab.com",
            "wss://relay.lawallet.ar",
            "wss://relay.timechaindex.com",
            "wss://relay.13room.space",
            "wss://relay.westernbtc.com",
            "wss://nostr.nobkslave.site",
            "wss://fiatjaf.nostr1.com",
            "wss://relay2.denostr.com",
            "wss://relay.nip05.social",
            "wss://bbb.santos.lol",
            "wss://relay.cosmicbolt.net",
        ]

    @classmethod
    def _postprocess_relays(cls, relays) -> List[str]:
        preferred_relays = cls.preferred_relays()
        return preferred_relays + [r for r in relays if r not in preferred_relays]

    @classmethod
    def get_relays(cls, nip: str = "4") -> List[str]:
        result = fetch_and_parse_json(f"https://api.nostr.watch/v1/nip/{nip}")
        logger.debug(f"fetch_and_parse_json returned {result}")
        if result:
            return cls._postprocess_relays(result)
        logger.debug(f"Return default list")
        return cls._postprocess_relays(cls.default_delays())


class BaseDM:
    def __init__(self, event: Event = None, use_compression=True) -> None:
        super().__init__()
        self.event = event
        self.use_compression = use_compression

    def dump(self) -> Dict:
        d = self.__dict__.copy()
        del d["use_compression"]
        d["event"] = self.event.as_json() if self.event else None
        return d

    def serialize(self) -> str:
        d = self.dump()
        if self.use_compression:
            # try to use as little space as possible
            # first encode the dict into cbor2, then compress,
            # which helps especially for repetative data
            # and then use base85 to (hopefully) use the space as best as possible
            cbor_serialized = cbor2.dumps(d)
            compressed_data = zlib.compress(cbor_serialized)
            base64_encoded_data = base64.b85encode(compressed_data).decode()
            return base64_encoded_data
        else:
            return json.dumps(d)

    @classmethod
    def from_dump(cls, decoded_dict: Dict, network: bdk.Network):
        # decode the data from the string and ensure the type is
        decoded_dict["event"] = Event.from_json(decoded_dict["event"]) if decoded_dict["event"] else None
        return cls(**decoded_dict)

    @classmethod
    def from_serialized(cls, base64_encoded_data: str, network: bdk.Network):

        if base64_encoded_data.startswith("{"):
            # if it is likely a json string, try this method first
            try:
                logger.debug(f"from_serialized json {base64_encoded_data}")
                decoded_dict = json.loads(base64_encoded_data)
                return cls.from_dump(decoded_dict, network=network)
            except Exception:
                logger.error(f"from_serialized: json.loads failed with {base64_encoded_data},  {network}")

        try:
            # try first the compressed decoding
            logger.debug(f"from_serialized compressed {base64_encoded_data}")
            decoded_data = base64.b85decode(base64_encoded_data)
            decompressed_data = zlib.decompress(decoded_data)
            decoded_dict = cbor2.loads(decompressed_data)
            return cls.from_dump(decoded_dict, network=network)
        except Exception:
            logger.error(f"from_serialized failed with {base64_encoded_data},  {network}")
            raise

    def __str__(self) -> str:
        return str(self.dump())

    def __eq__(self, other) -> bool:
        if isinstance(other, BaseDM):
            if bool(self.event) != bool(other.event):
                return False
            if self.event and other.event and self.event.as_json() != other.event.as_json():
                # logger.debug(str((self.event.as_json(),  other.event.as_json())))
                return False
            return True
        return False


class ProtocolDM(BaseDM):
    def __init__(
        self,
        public_key_bech32: str,
        please_trust_public_key_bech32: str = None,
        event: Event = None,
        use_compression=True,
    ) -> None:
        super().__init__(event=event, use_compression=use_compression)
        self.public_key_bech32 = public_key_bech32
        # this is only when I want the recipient to trust me back
        self.please_trust_public_key_bech32 = please_trust_public_key_bech32

    def __eq__(self, other) -> bool:
        if not super().__eq__(other):
            return False
        if isinstance(other, ProtocolDM):
            return (
                self.public_key_bech32 == other.public_key_bech32
                and self.please_trust_public_key_bech32 == other.please_trust_public_key_bech32
            )
        return False


class ChatLabel(enum.Enum):
    GroupChat = enum.auto()
    SingleRecipient = enum.auto()
    DistrustMeRequest = enum.auto()
    DeleteMeRequest = enum.auto()

    @classmethod
    def from_value(cls, value: int):
        return cls._value2member_map_.get(value)

    @classmethod
    def from_name(cls, name: str):
        return cls._member_map_.get(name)


class BitcoinDM(BaseDM):
    def __init__(
        self,
        label: ChatLabel,
        description: str,
        data: Data = None,
        intended_recipient: str = None,
        event: Event = None,
        use_compression=True,
    ) -> None:
        super().__init__(event=event, use_compression=use_compression)
        self.label = label
        self.description = description
        self.data = data
        self.intended_recipient = intended_recipient

    def dump(self) -> Dict:
        d = super().dump()
        d["label"] = self.label.value
        d["data"] = self.data.dump() if self.data else None
        return d

    @classmethod
    def from_dump(cls, d: Dict, network: bdk.Network) -> "BitcoinDM":
        d["label"] = ChatLabel.from_value(d.get("label", ChatLabel.GroupChat.value))
        d["data"] = Data.from_dump(d["data"], network=network) if d.get("data") else None
        return cls(**d)

    def __eq__(self, other) -> bool:
        if not super().__eq__(other):
            return False
        if isinstance(other, BitcoinDM):
            if self.label != other.label:
                return False
            if self.description != other.description:
                return False
            if bool(self.data) != bool(other.data):
                return False
            if self.data and other.data and self.data.data_as_string() != other.data.data_as_string():
                return False
            return True
        return False


class NotificationHandler(HandleNotification):
    def __init__(
        self,
        my_keys: Keys,
        get_allow_keys_bech32: Callable[[], set[str]],
        queue: deque,
        signal_dm: pyqtSignal,
        from_serialized: Callable[[str], BaseDM],
    ) -> None:
        super().__init__()
        self.queue = queue
        self.get_allow_keys_bech32 = get_allow_keys_bech32
        self.my_keys = my_keys
        self.signal_dm = signal_dm
        self.from_serialized = from_serialized

    def is_dm_for_me(self, event: Event) -> bool:
        if not event.kind().match_enum(KindEnum.ENCRYPTED_DIRECT_MESSAGE()):
            return False
        recipient_public_key = get_recipient_public_key(event)
        if not recipient_public_key:
            return False
        return recipient_public_key.to_bech32() == self.my_keys.public_key().to_bech32()

    def handle_dm_event(self, event: Event):
        recipient_public_key = get_recipient_public_key(event)
        if not recipient_public_key:
            return
        logger.debug(f"dm recipient {recipient_public_key.to_bech32()}, author {event.author().to_bech32()}")
        if not self.is_dm_for_me(event):
            logger.debug("dm is not for me")
            return

        if event.author().to_bech32() not in self.get_allow_keys_bech32():
            logger.debug(
                f"author {event.author().to_bech32()} is not in allowlist {self.get_allow_keys_bech32()}"
            )
            return

        base64_encoded_data = nip04_decrypt(self.my_keys.secret_key(), event.author(), event.content())
        # logger.debug(f"Decrypted dm to: {base64_encoded_data}")
        nostr_dm = self.from_serialized(base64_encoded_data)
        nostr_dm.event = event

        if self.dm_is_alreay_in_queue(nostr_dm):
            logger.debug(f"This nostr dm is already in the queue")
            return

        self.queue.append(nostr_dm)
        self.signal_dm.emit(nostr_dm)

        logger.debug(f"Processed dm: {nostr_dm}")

    def dm_is_alreay_in_queue(self, dm: BaseDM) -> bool:
        for item in list(self.queue):
            if not isinstance(item, BaseDM):
                continue
            if item == dm:
                return True
        return False

    def handle(self, relay_url: str, subscription_id: str, event: Event):
        # logger.debug(f"Received new event from {relay_url}: {event.as_json()}")
        # logger.debug("Decrypting event")
        try:
            self.handle_dm_event(event)
        except Exception as e:
            logger.error(f"Error during handle: {str(e)} of {relay_url}")

    def handle_msg(self, relay_url: str, msg: RelayMessage):
        pass
        # logger.debug(f"Received direct message: {msg}")


class DmConnection(QObject):
    def __init__(
        self,
        signal_dm: pyqtSignal,
        from_serialized: Callable[[str], BaseDM],
        keys: Keys,
        use_timer: bool = False,
        events: list[Event] = None,
        allow_list: list[str] = None,
        relay_list: RelayList = None,
    ) -> None:
        super().__init__()
        self.signal_dm = signal_dm
        self.use_timer = use_timer
        self.from_serialized = from_serialized
        self.allow_list = set(allow_list) if allow_list else set()
        self.minimum_connect_relays = 2
        self.relay_list = relay_list if relay_list else RelayList.from_internet()
        self.counter_no_connected_relay = 0

        self.keys: Keys = keys
        self.client: Client = None
        # self.queue stores received events and is also used for self.dump
        self.queue: deque[BaseDM] = deque(maxlen=10000)
        # self.events is used for replaying events from dump
        self.events: list[Event] = events if events else []
        self.current_subscription_dict: Dict[str, PublicKey] = {}  # subscription_id: PublicKey
        self.timer = QTimer()

        # Initialize the client with the private key
        self.client = None
        self.refresh_client()

    def refresh_client(self):
        if self.client:
            self.client.disconnect()

        signer = NostrSigner.keys(self.keys)
        self.client = Client(signer)

        self.notification_handler = NotificationHandler(
            self.keys,
            self.get_currently_allowed,
            self.queue,
            self.signal_dm,
            from_serialized=self.from_serialized,
        )
        self.client.handle_notifications(self.notification_handler)

    def get_currently_allowed(self) -> Set[str]:
        allow_list = set([k.to_bech32() for k in self.current_subscription_dict.values()])
        allow_list.add(self.keys.public_key().to_bech32())
        allow_list.update(self.allow_list)
        return allow_list

    def public_key_was_published(self, public_key: PublicKey) -> bool:
        for dm in list(self.queue):
            if isinstance(dm, ProtocolDM):
                if dm.public_key_bech32 == public_key.to_bech32():
                    return True
        return False

    def get_connected_relays(self) -> List[Relay]:
        connected_relays: List[Relay] = [
            relay for relay in self.client.relays().values() if relay.status() == RelayStatus.CONNECTED
        ]
        # logger.debug(f"connected_relays = {connected_relays} of all relays {self.client.relays()}")
        return connected_relays

    def send(self, dm: BaseDM, receiver: PublicKey) -> Optional[EventId]:
        self.ensure_connected()
        try:
            event_id = self.client.send_direct_msg(receiver, dm.serialize(), reply=None)
            logger.debug(f"sent {dm}")
            return event_id
        except Exception as e:
            logger.error(f"Error sending direct message: {e}")
            return None

    def _get_filter(self, recipient: PublicKey, author: PublicKey, start_time: datetime = None):
        this_filter = (
            Filter()
            .pubkeys([recipient])
            .authors([author])
            .kind(Kind.from_enum(KindEnum.ENCRYPTED_DIRECT_MESSAGE()))
        )
        if start_time:
            this_filter = this_filter.since(timestamp=Timestamp.from_secs(int(start_time.timestamp())))
        return this_filter

    def _filters(self, author_public_keys: List[PublicKey], start_time: datetime = None) -> dict[str, Filter]:
        recipient_public_key = self.keys.public_key()
        return {
            author_public_key.to_bech32(): self._get_filter(
                recipient=recipient_public_key,
                author=author_public_key,
                start_time=start_time,
            )
            for author_public_key in author_public_keys
        }

    def subscribe(self, public_key: PublicKey, start_time: datetime = None) -> str:
        "overwrites previous filters"
        if not self.get_connected_relays():
            self.ensure_connected()

        self._start_timer()

        subscription_id = self.client.subscribe(
            self._filters([public_key], start_time=start_time).values(), opts=None
        )
        self.current_subscription_dict[subscription_id] = public_key
        logger.debug(f"Added subscription_id {subscription_id} for public_key {public_key.to_bech32()}")
        return subscription_id

    def unsubscribe_all(self):
        self.unsubscribe(list(self.current_subscription_dict.values()))

    def unsubscribe(self, public_keys: List[PublicKey]):
        for subscription_id, pub_key in list(self.current_subscription_dict.items()):
            if pub_key in public_keys:
                self.client.unsubscribe(subscription_id)
                del self.current_subscription_dict[subscription_id]

    def _start_timer(self, delay_retry_connect=5):
        if not self.use_timer:
            return
        if self.timer.isActive():
            return
        self.timer.setInterval(delay_retry_connect * 1000)
        self.timer.timeout.connect(self.ensure_connected)
        self.timer.start()

    def ensure_connected(self):
        if len(self.get_connected_relays()) >= min(self.minimum_connect_relays, len(self.relay_list.relays)):
            return

        self.relay_list.update_if_stale()

        relay_subset = self.relay_list.get_subset(
            self.minimum_connect_relays + self.counter_no_connected_relay
        )
        self.client.add_relays(relay_subset)
        self.client.connect()
        logger.debug(
            f"add_relay {relay_subset}, currently get_connected_relays={self.get_connected_relays()}"
        )
        # assume the connections are successfull
        # however if not, then next time try 1 more connection
        sleep(0.1)
        self.counter_no_connected_relay += 1

    def dump(
        self,
        forbidden_data_types: List[DataType] = None,
    ):
        def include_item(item: BaseDM) -> bool:
            if isinstance(item, BitcoinDM):
                if forbidden_data_types is not None:
                    if item.data and item.data.data_type in forbidden_data_types:
                        return False
            if isinstance(item, ProtocolDM):
                return False
            return True

        return {
            "use_timer": self.use_timer,
            "keys": self.keys.secret_key().to_bech32(),
            "events": [item.event.as_json() for item in self.queue if item.event and include_item(item)],
            "allow_list": list(self.get_currently_allowed()),
            "relay_list": self.relay_list.dump(),
        }

    @classmethod
    def from_dump(
        cls, d: Dict, signal_dm: pyqtSignal, from_serialized: Callable[[str], BaseDM]
    ) -> "DmConnection":
        d["keys"] = Keys(secret_key=SecretKey.from_bech32(d["keys"]))

        d["events"] = [Event.from_json(json_item) for json_item in d["events"]]
        d["relay_list"] = RelayList.from_dump(d["relay_list"]) if "relay_list" in d else None

        return DmConnection(**d, signal_dm=signal_dm, from_serialized=from_serialized)

    def replay_events(self):
        # now handle the events as if they came from a relay
        for event in self.events:
            self.notification_handler.handle(relay_url="from_storage", event=event, subscription_id="replay")


class BaseProtocol(QObject):
    signal_dm = pyqtSignal(BaseDM)

    def __init__(
        self,
        keys: Keys = None,
        dm_connection_dump: dict = None,
        start_time: datetime = None,
    ) -> None:
        "Either keys or dm_connection_dump must be given"
        super().__init__()
        self.start_time = start_time

        self.dm_connection = (
            DmConnection.from_dump(
                d=dm_connection_dump,
                signal_dm=self.signal_dm,
                from_serialized=self.from_serialized,
            )
            if dm_connection_dump
            else DmConnection(self.signal_dm, from_serialized=self.from_serialized, keys=keys)
        )

    @abstractmethod
    def subscribe(self):
        pass

    @abstractmethod
    def from_serialized(self, base64_encoded_data) -> BaseDM:
        pass

    def refresh_dm_connection(self, keys: Keys = None, relay_list: RelayList = None):
        keys = keys if keys else self.dm_connection.keys
        relay_list = relay_list if relay_list else self.dm_connection.relay_list

        self.dm_connection.client.disconnect()
        self.dm_connection.keys = keys
        self.dm_connection.relay_list = relay_list
        self.start_time = None
        self.dm_connection.refresh_client()
        # self.dm_connection = DmConnection(
        #     self.signal_dm, from_serialized=self.from_serialized, keys=keys, relay_list=relay_list
        # )
        self.subscribe()

    def set_relay_list(self, relay_list: RelayList):
        self.refresh_dm_connection(relay_list=relay_list)


class NostrProtocol(BaseProtocol):
    signal_dm = pyqtSignal(ProtocolDM)

    def __init__(
        self,
        network: bdk.Network,
        keys: Keys = None,
        dm_connection_dump: Dict = None,
        start_time: datetime = None,
        use_compression=True,
    ) -> None:
        "Either keys or dm_connection_dump must be given"
        self.network = network
        super().__init__(keys=keys, dm_connection_dump=dm_connection_dump, start_time=start_time)
        self.use_compression = use_compression

    def from_serialized(self, base64_encoded_data) -> ProtocolDM:
        return ProtocolDM.from_serialized(base64_encoded_data=base64_encoded_data, network=self.network)

    def list_public_keys(self):
        pass

    def publish_public_key(self, author_public_key: PublicKey, force=False):
        logger.debug(f"starting publish_public_key {self.dm_connection.keys.public_key().to_bech32()}")
        if not force and self.dm_connection.public_key_was_published(author_public_key):
            logger.debug(f"{author_public_key.to_bech32()} was published already. No need to do it again")
            return
        dm = ProtocolDM(
            public_key_bech32=author_public_key.to_bech32(), event=None, use_compression=self.use_compression
        )
        self.dm_connection.send(dm, self.dm_connection.keys.public_key())
        logger.debug(f"done publish_public_key {self.dm_connection.keys.public_key().to_bech32()}")

    def publish_trust_me_back(self, author_public_key: PublicKey, recipient_public_key: PublicKey):
        dm = ProtocolDM(
            public_key_bech32=author_public_key.to_bech32(),
            please_trust_public_key_bech32=recipient_public_key.to_bech32(),
            event=None,
            use_compression=self.use_compression,
        )
        self.dm_connection.send(dm, self.dm_connection.keys.public_key())

    def subscribe(self):
        self.dm_connection.subscribe(self.dm_connection.keys.public_key(), start_time=self.start_time)

    def dump(self):
        return {
            # the next starttime is the current time
            "start_time": datetime.now().timestamp(),
            "dm_connection_dump": self.dm_connection.dump(),
        }

    @classmethod
    def from_dump(cls, d: Dict, network: bdk.Network, use_compression=True) -> "NostrProtocol":
        d["start_time"] = datetime.fromtimestamp(d["start_time"])

        return NostrProtocol(**d, network=network, use_compression=use_compression)


class GroupChat(BaseProtocol):
    """This should be replaced with https://github.com/nostr-protocol/nips/blob/master/44.md
    https://docs.rs/nostr-sdk/0.27.0/nostr_sdk/prelude/nip44/fn.encrypt.html
    """

    signal_dm = pyqtSignal(BitcoinDM)

    def __init__(
        self,
        network: bdk.Network,
        keys: Keys = None,
        dm_connection_dump: dict = None,
        start_time: datetime = None,
        members: List[PublicKey] = None,
        use_compression=True,
    ) -> None:
        "Either keys or dm_connection_dump must be given"
        self.members: List[PublicKey] = members if members else []
        self.network = network
        self.use_compression = use_compression
        super().__init__(
            keys=keys,
            dm_connection_dump=dm_connection_dump,
            start_time=start_time,
        )

    def from_serialized(self, base64_encoded_data: str) -> BitcoinDM:
        return BitcoinDM.from_serialized(base64_encoded_data, network=self.network)

    def add_member(self, new_member: PublicKey):
        if new_member.to_bech32() not in [k.to_bech32() for k in self.members]:
            self.members.append(new_member)
            self.dm_connection.subscribe(new_member)
            logger.debug(f"Add {new_member.to_bech32()} as trusted")

    def remove_member(self, remove_member: PublicKey):
        members_bech32 = [k.to_bech32() for k in self.members]
        if remove_member.to_bech32() in members_bech32:
            self.members.pop(members_bech32.index(remove_member.to_bech32()))
            self.dm_connection.unsubscribe([remove_member])
            logger.debug(f"Removed {remove_member.to_bech32()}")

    def send(self, dm: BitcoinDM, send_also_to_me=True):
        recipients = self.members_including_me() if send_also_to_me else self.members
        for public_key in recipients:
            self.dm_connection.send(dm, public_key)
            logger.debug(f"Send to {public_key.to_bech32()}")

        if not self.members:
            logger.debug(f"Sending not done, since self.members is empty")

    def members_including_me(self):
        return self.members + [self.dm_connection.keys.public_key()]

    def subscribe(self):
        for public_key in self.members_including_me():
            self.dm_connection.subscribe(public_key, start_time=self.start_time)

    def dump(self):
        forbidden_data_types = [DataType.LabelsBip329]
        return {
            # the next starttime is the current time
            "start_time": datetime.now().timestamp(),
            "dm_connection_dump": self.dm_connection.dump(forbidden_data_types=forbidden_data_types),
            "members": [member.to_bech32() for member in self.members],
        }

    @classmethod
    def from_dump(cls, d: Dict, network: bdk.Network, use_compression=True) -> "NostrProtocol":
        d["start_time"] = datetime.fromtimestamp(d["start_time"])

        d["members"] = [PublicKey.from_bech32(pk) for pk in d["members"]]
        return GroupChat(**d, network=network, use_compression=use_compression)

    def renew_own_key(self):
        # send new key to memebers
        for member in self.members:
            self.dm_connection.send(
                BitcoinDM(
                    event=None,
                    label=ChatLabel.DeleteMeRequest,
                    description="",
                    use_compression=self.use_compression,
                ),
                member,
            )
            # self.dm_connection.send(ProtocolDM(event=None, public_key_bech32=keys.public_key().to_bech32(),please_trust_public_key_bech32=True), member)
            # logger.debug(f"Send my new public key {keys.public_key().to_bech32()} to {member.to_bech32()}")

        self.refresh_dm_connection(Keys.generate())
