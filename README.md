# A Nostr Chat with participant discovery

All users know a shared secret (like a bitcoin wallet descriptor). This allows them to find each other. 
  * Even if this shared secret leaks, the attacker can only spam the discovery option, the actual chats stay secure

The actual single and group chats are based on a newly generated secret keys for each participant.
  * Each participant has to be manually accepted to be added to the group chat
  * Chats with participants use NIP17 and group messages are simply NIP17 messages to each participant 

Export and restoring of the nsec and with it restoration of all messages of the relays







# Protocol

## Setup

Each participant creates their own random secret nsec (called `nsecparticipant`).

### Nostr Message Content

All nostr messages have have optional [compression](https://github.com/andreasgriffin/bitcoin-nostr-chat/blob/bcdeb0659c3bb9dfeec4987d9b228460338fa0f2/bitcoin_nostr_chat/base_dm.py#L75) (recommended) for their content. 

#### Compression

All exchanged [messages](https://github.com/andreasgriffin/bitcoin-nostr-chat/blob/bcdeb0659c3bb9dfeec4987d9b228460338fa0f2/bitcoin_nostr_chat/base_dm.py#L50) need to have at least `"created_at"` key with a unix timestamp, to ensure correct ordering of chat messages

```python
d = {"created_at": 1746003358}
cbor_serialized = cbor2.dumps(d)
compressed_data = zlib.compress(cbor_serialized)
compressed_message_content = base64.b85encode(compressed_data).decode()
```

#### No Compression

Message content example: 

```python
compressed_message_content = {"created_at": 1746003358}
```



## Participant discovery

#### `nsecshared` construction

Because `sortedmulti`  descriptors are not unique

- any order of the xpubs is ok
- not even all fingerprints need to be correct for a watch only wallet
-  multipath/not multipath describe essentially the same wallet

 one cannot use the descriptor directly to derive `nsecshared`

It is derived as:

````python
xpubs = ['xpub....', 'xpub....']
default_key_origin = "m/48h/0h/0h/1h" # using hardened_char="h", not "'"
total_string = default_key_origin + "".join(sorted(xpubs))
hashed_once = hashlib.sha256(total_string.encode()).hexdigest()
hashed_twice = hashlib.sha256(hashed_once.encode()).hexdigest() 
nsecshared = nostr_sdk.SecretKey.parse(hashed_twice)
````

#### `nsecparticipant` announcement

Announcement [messages](https://github.com/andreasgriffin/bitcoin-nostr-chat/blob/bcdeb0659c3bb9dfeec4987d9b228460338fa0f2/bitcoin_nostr_chat/protocol_dm.py#L42) are sent as Nip17 messages to `npubshared` using the `nsecshared` (author and receiver are identical).

Content (with optional compression):

````python
 {"created_at": 1746003358, public_key_bech32:"npubparticipant", }
````

optional fields are:

- `"please_trust_public_key_bech32": npubother` :  Is  request that `npubother` should check if he trusts `npubparticipant`

## Chat Messages

Once `nsecparticipant` (me) trusts `npubother` I send and receive nip17 [messages](https://github.com/andreasgriffin/bitcoin-nostr-chat/blob/a0e16671308822442f313f686174d2c46b6231e2/bitcoin_nostr_chat/bitcoin_dm.py#L61) to/from him.

Message content:

````python
 {"created_at": 1746003358, "label":1,  "description": "Hello world"}
````

* `"label"` is an [enum](https://github.com/andreasgriffin/bitcoin-nostr-chat/blob/a0e16671308822442f313f686174d2c46b6231e2/bitcoin_nostr_chat/bitcoin_dm.py#L46).  `1=GroupChat` (default),   `2=SingleRecipient` is indicating that the message should not be displayed in a group chat window, but is only sent to the single receiver. `3=DistrustMeRequest`  says that `nsecparticipant` is compromised and should not be trusted. `4=DeleteMeRequest`  says that `nsecparticipant` is compromised and it should also be hidden in the participant discovery. 
* `"description"` is a string that is displayed as a chat message

### Optional fields

- ##### Label data

  ````python
   "data": {
       'data': '{"__class__": "Label", "VERSION": "0.0.3", "type": "addr", "ref": "tb1q3qt0n3z69sds3u6zxalds3fl67rez4u2vjv6we", "label": "I am an adddress label", "timestamp": 1746003358}\n{"__class__": "Label", "VERSION": "0.0.3", "type": "addr", "ref": "tb1qmx7ke6j0amadeca65xqxpwh0utju5g3u55na9a", "label": "I am an adddress label too", "timestamp": 1746003358}'
  ,
       'data_type': 'LabelsBip329'
   }
  ````

  - even though it says `'data_type': 'LabelsBip329'` this protocol requires more than Bip329
    - `"__class__": "Label"` is required and indicates the presence of `"VERSION", "timestamp" ` fields
    - `"timestamp"` is required, since it is crucial to know if this label update is newer than the one already present in the wallet
    - `"VERSION": "0.0.3"` is required, and is important, since it allows for graceful upgrading, which is crucial in a protocol, where all participants are not necessarily on the latest version, and where relays store old messages.
  - other fields may be included (may be ignored by clients)  in each json line
  - optional field `"category"`, e.g.:
    - `'{"__class__": "Label", "VERSION": "0.0.3", "type": "addr", "ref": "tb1q3qt0n3z69sds3u6zxalds3fl67rez4u2vjv6we", "label": "I am an adddress label", "timestamp": 1746003358, "category": "I am a coin category"}'`
  - Splitting: hundreds of labels (even with compression), can lead to messages exceeding the nostr dm limits. Therefore one can [split](https://github.com/andreasgriffin/bitcoin-safe/blob/1d5959363b718c7b5d593514115bb28dc48740ca/bitcoin_safe/gui/qt/label_syncer.py#L99) the json lines to stay way under the limit.

- ##### Transaction 

  ````python
   "data": { 
       'data': '02000000000101fc236001ebf5172397b92d411bfbf5ff51f08686e2443e248d0c2ed216d6ef070000000000fdffffff012709000000000000160014cbcd06e51299d26952ceed9b22fda644aa7df1220247304402203cb08c4b6b6410ed5b49532059c2ba6f525c2e59bf0edb013f830876f5ee0da702206f8e97552d0f8a6b0359431b58395aa42dc1ca12d26a1b8ca184cfd9e87187ef012102581ea439b4a084c2945eec9b57da1621c5792b4209eab4fd26c284720219ebb7070c0000', 
    	'data_type': 'Tx'
   }
  ````


- ##### PSBT 

  ````python
  "data": { 
      'data': 'cHNidP8BAJoCAAAA....AAA', 
      'data_type': 'PSBT'
  }
  ````

- ##### SignMessageRequest

  The format is identical to: https://coldcard.com/docs/message-signing/

  ````python
  "data": { 
      'data': '{"msg":"test message", "subpath": "m/84h/0h/0h/0/10","addr_fmt": "p2wpkh"}', 
      'data_type': 'SignMessageRequest'
  }
  ````

- ##### Other data types see [here](https://github.com/andreasgriffin/bitcoin-qr-tools/blob/afc9d6c552838d02e48f02abe69905116d372a5d/bitcoin_qr_tools/data.py#L33) and the serialization [here](https://github.com/andreasgriffin/bitcoin-qr-tools/blob/afc9d6c552838d02e48f02abe69905116d372a5d/bitcoin_qr_tools/data.py#L774)



Please contact me if you have any questions.

