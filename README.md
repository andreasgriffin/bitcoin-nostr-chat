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

All nostr messages have have optional [compression](https://github.com/andreasgriffin/bitcoin-nostr-chat/blob/5e166054d6a38f3becab0b84d6a8b01c0fcb0fb1/bitcoin_nostr_chat/base_dm.py#L75) (recommended) for their content. 

#### Compression

All exchanged [messages](https://github.com/andreasgriffin/bitcoin-nostr-chat/blob/5e166054d6a38f3becab0b84d6a8b01c0fcb0fb1/bitcoin_nostr_chat/base_dm.py#L50) need to have at least `"created_at"` key with a unix timestamp (float), to ensure correct ordering of chat messages

```python
import cbor2, zlib, base64

def compress(d:dict) -> str:
    cbor_serialized = cbor2.dumps(d)	# b'\xa1jcreated_at\x1ah\x11\xe5\x9e'
    compressed_data = zlib.compress(cbor_serialized)	# b'x\x9c[\x98\x95\\\x94\x9aX\x92\x9a\x12\x9fX"\x95!\xf8t\x1e\x00@\x9e\x07.'
    return base64.b85encode(compressed_data).decode()
message_content = compress({"created_at": 1746003358})	# 'c${09m0XmXSdy9&pI9Q5A^3D206?AxE&'
```

```python
def decompress(s:str) -> dict:
    decoded_data = base64.b85decode(base85_encoded_data)
    decompressed_data = zlib.decompress(decoded_data)
    return cbor2.loads(decompressed_data)
decompress('c${09m0XmXSdy9&pI9Q5A^3D206?AxE&')	# {"created_at": 1746003358}
```

#### No Compression

Message content example: 

```python
message_content = {"created_at": 1746003358}
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
xpubs = ['tpub....', 'tpub....']
default_key_origin = 'm/84h/1h/0h'	# using hardened_char="h", not "'"
total_string = default_key_origin + "".join(sorted(xpubs))	# 'm/84h/1h/0htpub....tpub....'
hashed_once = hashlib.sha256(total_string.encode()).hexdigest()	# f5e23e3fdf6aa18b97535c22e0f42541fc60a39565faf7127954c80f8ddcc974
hashed_twice = hashlib.sha256(hashed_once.encode()).hexdigest()	# '1e3526e27654cbe32890b171b4a44db3a8c9fe14f17493dc9af22d4224a3d6a4'
nsecshared = nostr_sdk.SecretKey.parse(hashed_twice)	# 'nsec1rc6jdcnk2n97x2ysk9cmffzdkw5vnls5796f8hy67gk5yf9r66jq24e366'
````

- `xpubs` is a list of xpubs occurring in the descriptor
- `default_key_origin` is the key origin that is standard for the [address type](https://github.com/andreasgriffin/bitcoin-usb/blob/59d4ee5987e48657ae5903f5bbfe982a0be8bfa8/bitcoin_usb/address_types.py#L107) of the wallet.  Example: [p2sh-p2wsh](https://bips.dev/48/): `default_key_origin = "m/48h/0h/0h/1h"`

#### `npubparticipant` announcement

Announcement [messages](https://github.com/andreasgriffin/bitcoin-nostr-chat/blob/5e166054d6a38f3becab0b84d6a8b01c0fcb0fb1/bitcoin_nostr_chat/annoucement_dm.py#L42) are sent as Nip17 messages to `npubshared` with author `nsecshared` (author and receiver are identical).

Content (before optional compression):

````python
 {"created_at": 1746003358, public_key_bech32:"npubparticipant", }
````

Optional fields are:

- `"please_trust_public_key_bech32": npubother` :  Is  request that `npubother` should check if he trusts `npubparticipant`. Recommended use: `npubparticipant` just marked  `npubother` as trusted and sends `"please_trust_public_key_bech32": npubother`.  `npubother`  can now get a visual notification that  `npubparticipant` requests his trust.   One way to visualize this request is to highlight `npubparticipant`  temporarily. 

## Chat Messages

Once `nsecparticipant` (me) trusts `npubother` I send and receive nip17 [messages](https://github.com/andreasgriffin/bitcoin-nostr-chat/blob/5e166054d6a38f3becab0b84d6a8b01c0fcb0fb1/bitcoin_nostr_chat/chat_dm.py#L61) to/from him.

- For Nip17 is crucial to unwrap all Nip17 messages to `npubparticipant`  and verify  `npubother == unwrapped_gift.sender()` 

Message content:

````python
 {"created_at": 1746003358, "label":1,  "description": "Hello world"}
````

* `"label"` is an [enum](https://github.com/andreasgriffin/bitcoin-nostr-chat/blob/5e166054d6a38f3becab0b84d6a8b01c0fcb0fb1/bitcoin_nostr_chat/chat_dm.py#L46).  `1=GroupChat` (default),   `2=SingleRecipient` is indicating that the message should not be displayed in a group chat window, but is only sent to the single receiver. `3=DistrustMeRequest`  says that `nsecparticipant` is compromised and should not be trusted. `4=DeleteMeRequest`  says that `nsecparticipant` is compromised and it should also be hidden in the participant discovery. 
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



##  JS examples

The **python** code snippets above are the reference implementation.  The code snippets below are just to ease testing for developers

#### Compression and Decompression

``` javascript
const cbor = require('cbor');
const pako = require('pako');

// Python’s base85 alphabet for b85encode:
const BASE85 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~';

const BASE85_DECODE = Object.fromEntries(
  BASE85.split('').map((ch, i) => [ch, i])
);

function base85Decode(str) {
  const len = str.length;
  const rem = len % 5;
  if (rem === 1) {
    throw new Error(`Invalid Base85 string length: mod 5 = ${rem}`);
  }
  // how many pad-chars we need to add to make a full 5-char block
  const padChars = rem ? 5 - rem : 0;
  // this is also the number of bytes the encoder originally padded (and then dropped)
  const padBytes = padChars;

  // pad the final, short group with the highest symbol ('~', value = 84)
  const padChar = BASE85[84];
  const full = padChars
    ? str + padChar.repeat(padChars)
    : str;

  const out = [];
  for (let i = 0; i < full.length; i += 5) {
    let acc = 0;
    for (let j = 0; j < 5; j++) {
      const ch = full[i + j];
      const val = BASE85_DECODE[ch];
      if (val === undefined) {
        throw new Error(`Invalid character '${ch}' at position ${i + j}`);
      }
      acc = acc * 85 + val;
    }
    // unpack into four bytes (big-endian)
    out.push((acc >>> 24) & 0xFF);
    out.push((acc >>> 16) & 0xFF);
    out.push((acc >>>  8) & 0xFF);
    out.push( acc         & 0xFF);
  }

  // drop the same number of padding _bytes_ that were added during encoding
  return Buffer.from(out.slice(0, out.length - padBytes));
}





function base85Encode(buf) {
  // pad to 4-byte boundary
  const pad = (4 - (buf.length % 4)) % 4;
  const data = pad ? Buffer.concat([buf, Buffer.alloc(pad)], buf.length + pad) : buf;

  let out = '';
  for (let i = 0; i < data.length; i += 4) {
    // read 4 bytes as a big-endian uint32
    let acc = data.readUInt32BE(i);
    let chunk = '';
    // turn into 5 base-85 chars
    for (let j = 0; j < 5; j++) {
      chunk = BASE85[acc % 85] + chunk;
      acc = Math.floor(acc / 85);
    }
    out += chunk;
  }
  // drop padding characters
  return pad ? out.slice(0, out.length - pad) : out;
}



///////////////////////////////////////
console.log('Compression');
///////////////////////////////////////


function compress(data ){
  try {
    const cborData = cbor.encode(data)
    //const cborData = cborSerialize(data)
    jsonUint8 = new Uint8Array(cborData)

    // it works if we skip the cborSerialization but outputs a different string
    //const jsonString = JSON.stringify(data)
    //jsonUint8 = new TextEncoder().encode(jsonString)

    const compressedData = pako.deflate(jsonUint8)
    const compressedBuffer = Buffer.from(compressedData)
    console.log("compressedBuffer: ", compressedBuffer);

    return base85Encode(compressedBuffer)
  } catch (error) {
    console.error('Compression error:', error)
    throw new Error('Failed to compress data')
  }
}


const d = { created_at: 1746003358 };
compressed_string = compress(d);
console.log(compressed_string);



///////////////////////////////////////
console.log('Decompression');
///////////////////////////////////////

function decompress(compressedString) {
  try {
    // 1) Base85 → Uint8Array
    const compressedBytes = base85Decode(compressedString);
    console.log("compressedBuffer: ", compressedBytes);

    // 2) Inflate → Uint8Array of cbor bytes
    const cborBytes = pako.inflate(compressedBytes);
    console.log(cborBytes);

    // 3) Decode cbor → original object
    return cbor.decode(Buffer.from(cborBytes));
  } catch (err) {
    console.error('Decompression error:', err);
    process.exit(1);
  }
}

// Example usage:
decompressed_str = decompress(compressed_string);
console.log('Decompressed:', decompressed_str);

```





Please contact me if you have any questions.



# Nostr subscription and message handling

## Group chat

It is crucial to separate **announcements**  from **group chat**.  Bitcoin Safe does it the following way:

- I announce my public key by sending the "`npubparticipant` announcement" message to `npubshared`
- **Subscription1** listens to messages sent to `npubshared` 
  - I announce my `npubparticipant`
  - If I receive a message that announces `npubother` one can add it to an `untrusted` list

* The application now presents the option to the user to trust  `npubother`
  * Once trusted, `npubother` is removed from the `untrusted` list and added to the `member` list. The `member` list is a locally stored list and not shared with anyone. The user has the option to remove a member at any time.
* **Subscription2** listens to all messages sent to `npubparticipant`
  * If the author (in NIP17 one needs to unwrap first) is in the `member` list, the message is accepted, otherwise the message is ignored



# Protocol Use cases

## Participant discovery

- One can not only derive the shared secret from a descriptor, but from all kinds of commonly known private information. The user has to manually trust the other device

## Chat messages

* **Label backup** can be realized with sending messages to yourself, and using the relay as a cloud backup (unreliable)
  * A -> A
* **Group chat** can be realized with sending messages to all other participants
  * A -> B,C,D,...

* **Label synchronization** is  just a special form of group chat message
  * After a new participant E is added, all labels are sent  A->E  (all labels)
  * After each label change, only this label  change is sent A->E  (saves bandwidth)
* **Collaborative signing** of a multisig PSBT. 
  * Distributes participants (or devices) can sign a PSBT one after another until all signatures are collected

* **Simple Chat** with only 2 participants is a special case of a group chat 





