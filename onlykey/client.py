# coding: utf-8
import logging
import time
import binascii
import hashlib
import os

import hid
from aenum import Enum
from sys import platform

log = logging.getLogger(__name__)

DEVICE_IDS = [
    (0x16C0, 0x0486),  # OnlyKey
    (0x1d50, 0x60fc),  # OnlyKey
]

if os.name== 'nt':
	MAX_INPUT_REPORT_SIZE = 65
	MATX_OUTPUT_REPORT_SIZE = 65
	MESSAGE_HEADER = [0, 255, 255, 255, 255]
else:
	MAX_INPUT_REPORT_SIZE = 64
	MATX_OUTPUT_REPORT_SIZE = 64
	MESSAGE_HEADER = [255, 255, 255, 255]

MAX_FEATURE_REPORTS = 0
MAX_LARGE_PAYLOAD_SIZE = 58  # 64 - <4 bytes header> - <1 byte message> - <1 byte size|0xFF if max>


SLOTS_NAME= {
    1: '1a',
    2: '2a',
    3: '3a',
    4: '4a',
    5: '5a',
    6: '6a',
    7: '1b',
    8: '2b',
    9: '3b',
    10: '4b',
    11: '5b',
    12: '6b',
    25: 'RSA Key 1',
    26: 'RSA Key 2',
    27: 'RSA Key 3',
    28: 'RSA Key 4',
    29: 'ECC Key 1',
    30: 'ECC Key 2',
    31: 'ECC Key 3',
    32: 'ECC Key 4',
    33: 'ECC Key 5',
    34: 'ECC Key 6',
    35: 'ECC Key 7',
    36: 'ECC Key 8',
    37: 'ECC Key 9',
    38: 'ECC Key 10',
    39: 'ECC Key 11',
    40: 'ECC Key 12',
    41: 'ECC Key 13',
    42: 'ECC Key 14',
    43: 'ECC Key 15',
    44: 'ECC Key 16',
    45: 'ECC Key 17',
    46: 'ECC Key 18',
    47: 'ECC Key 19',
    48: 'ECC Key 20',
    49: 'ECC Key 21',
    50: 'ECC Key 22',
    51: 'ECC Key 23',
    52: 'ECC Key 24',
    53: 'ECC Key 25',
    54: 'ECC Key 26',
    55: 'ECC Key 27',
    56: 'ECC Key 28',
    57: 'ECC Key 29',
    58: 'ECC Key 30',
    59: 'ECC Key 31',
    60: 'ECC Key 32',
}


class Message(Enum):
    OKSETPIN = 225  # 0xE1
    OKSETSDPIN = 226  # 0xE2
    OKSETPDPIN = 227  # 0xE3
    OKSETTIME = 228  # 0xE4
    OKGETLABELS = 229  # 0xE5
    OKSETSLOT = 230  # 0xE6
    OKWIPESLOT = 231  # 0xE7
    OKSETU2FPRIV = 232  # 0xE8
    OKWIPEU2FPRIV = 233  # 0xE9
    OKSETU2FCERT = 234  # 0xEA
    OKWIPEU2FCERT = 235  # 0xEB
    OKGETPUBKEY = 236
    OKSIGNCHALLENGE = 237
    OKWIPEPRIV = 238
    OKSETPRIV = 239
    OKDECRYPT = 240
    OKRESTORE = 241


class MessageField(Enum):
    LABEL = 1
    URL = 15
    DELAY1 = 17
    NEXTKEY4 = 18
    USERNAME = 2
    NEXTKEY1 = 16
    NEXTKEY2 = 3
    DELAY2 = 4
    PASSWORD = 5
    NEXTKEY3 = 6
    DELAY3 = 7
    NEXTKEY5 = 19
    TFATYPE = 8
    TOTPKEY = 9
    YUBIAUTH = 10
    IDLETIMEOUT = 11
    WIPEMODE = 12
    KEYTYPESPEED = 13
    KEYLAYOUT = 14
    LEDBRIGHTNESS = 24
    SECPROFILEMODE = 23
    PGPCHALENGEMODE = 22
    SSHCHALENGEMODE = 21
    BACKUPMODE = 20

class KeyTypeEnum(Enum):
    ED22519 = 1
    P256 = 2
    SECP256K1 = 3

class OnlyKeyUnavailableException(Exception):
    """Exception raised when the connection to the OnlyKey failed."""
    pass


class Slot(object):
    def __init__(self, num, label=''):
        self.number = num
        self.label = label
        self.name = SLOTS_NAME[num]

    def __repr__(self):
        return '<Slot \'{}|{}\'>'.format(self.name, self.label)

    def to_str(self):
        return 'Slot {}: {}'.format(self.name, self.label or '<empty>')

class OnlyKey(object):
    def __init__(self, connect=True):
        if connect:
            tries = 5
            while tries > 0:
                try:
                    self._connect()
                    log.debug('connected')
                    return
                except Exception as e:
                    log.debug('connect failed, trying again in 1 second...')
                    time.sleep(1.5)
                    tries -= 1

            raise e

    def _connect(self):
        try:
            for d in hid.enumerate(0, 0):
                vendor_id = d['vendor_id']
                product_id = d['product_id']
                serial_number = d['serial_number']
                interface_number = d['interface_number']
                usage_page = d['usage_page']
                path = d['path']

                if (vendor_id, product_id) in DEVICE_IDS:
                    if serial_number == '1000000000':
                        if usage_page == 0xffab or interface_number == 2:
                            self._hid = hid.Device(vendor_id, product_id, path=path)
                            self._hid.nonblocking = True
                    else:
                        if usage_page == 0xf1d0 or interface_number == 1:
                            self._hid = hid.Device(vendor_id, product_id, path=path)
                            self._hid.nonblocking = True

        except:
            log.exception('failed to connect')
            raise OnlyKeyUnavailableException()

    def close(self):
        return self._hid.close()

    def initialized(self):
        return self.read_string() == 'INITIALIZED'

    def set_time(self, timestamp):
        # Hex format without leading 0x
        current_epoch_time = format(int(timestamp), 'x')
        # pad with zeros for even digits
        current_epoch_time = current_epoch_time.zfill(len(current_epoch_time) + len(current_epoch_time) % 2)
        log.debug('Setting current epoch time =', current_epoch_time)
        payload = [int(current_epoch_time[i: i+2], 16) for i in range(0, len(current_epoch_time), 2)]

        log.debug('SENDING OKSETTIME:', [x for x in enumerate(payload)]);
        self.send_message(msg=Message.OKSETTIME, payload=payload)

    def set_ecc_key(self, key_type, slot, key):
        payload = bytes([key_type, slot]) + key
        self.send_message(msg=Message.OKSETPRIV, payload=payload)

    def set_rsa_key(self, key_type, slot, key):
        payload = [key_type, slot] + [ord(c) for c in key]
        self.send_message(msg=Message.OKSETPRIV, payload=payload)

    def send_message(self, payload=None, msg=None, slot_id=None, message_field=None):
        """Send a message."""
        log.debug('preparing payload for writing')
        # Initialize an empty message with the header
        raw_bytes = bytes(MESSAGE_HEADER)

        # Append the message type (must be `Message` enum value)
        if msg:
            log.debug('msg=%s', msg.name)
            raw_bytes += bytes([msg.value])

        # Append the slot ID if needed
        if slot_id:
            log.debug('slot_id=%s', slot_id)
            raw_bytes += bytes([slot_id])

        # Append the message field (must be a `MessageField` enum value)
        if message_field:
            log.debug('slot_field=%s', message_field.name)
            raw_bytes += bytes([message_field.value])

        # Append the raw payload, expect a string or a list of int
        if payload:
            if isinstance(payload, bytes):
                log.debug("payload=%s", payload)
                raw_bytes += payload
            elif isinstance(payload, str):
                log.debug('payload="%s"', payload)
                raw_bytes += payload.encode("utf-8")
            elif isinstance(payload, list):
                log.debug('payload=%s', ''.join([chr(c) for c in payload]))
                raw_bytes += bytes(payload)
            elif isinstance(payload, int):
                log.debug('payload=%d', payload)
                raw_bytes += bytes([payload])
            else:
                raise Exception('`payload` must be either `str` or `list`, got `{}`'.format(type(payload)))
        # Pad the ouput with 0s
        while len(raw_bytes) < MAX_INPUT_REPORT_SIZE:
            raw_bytes += bytes([0])

        # Send the message
        log.debug('sending message ')
        self._hid.write(raw_bytes)

    def send_large_message(self, payload=None, msg=None, slot_id=chr(101)):
        """Wrapper for sending large message (larger than 58 bytes) in batch in a transparent way."""
        if not msg:
            raise Exception("Missing msg")

        # Split the payload in multiple chunks
        chunks = [payload[x:x+MAX_LARGE_PAYLOAD_SIZE] for x in range(0, len(payload), 58)]
        for chunk in chunks:
            # print chunk
            # print [ord(c) for c in chunk]
            current_payload = bytes([255])  # 255 means that it's not the last payload
            # If it's less than the max size, set explicitely the size
            if len(chunk) < 58:
                current_payload = bytes([len(chunk)])

            # Append the actual payload
            if isinstance(chunk, list):
                current_payload += bytes(chunk)
            else:
                current_payload += chunk

            self.send_message(payload=current_payload, msg=msg)


    def send_large_message2(self, payload=None, msg=None, slot_id=101):
        """Wrapper for sending large message (larger than 58 bytes) in batch in a transparent way."""
        if not msg:
            raise Exception("Missing msg")

        # Split the payload in multiple chunks
        chunks = [payload[x:x+MAX_LARGE_PAYLOAD_SIZE-1] for x in range(0, len(payload), 57)]
        for chunk in chunks:
            # print chunk
            # print [ord(c) for c in chunk]
            current_payload = [slot_id, 255]  # 255 means that it's not the last payload
            # If it's less than the max size, set explicitely the size
            if len(chunk) < 57:
                current_payload = [slot_id, len(chunk)]

            current_payload = bytes(current_payload)

            # Append the actual payload
            if isinstance(chunk, list):
                current_payload += bytes(chunk)
            else:
                current_payload += chunk

            self.send_message(payload=current_payload, msg=msg)


    def send_large_message3(self, payload=None, msg=None, slot_id=101, key_type=1):
        """Wrapper for sending large message (larger than 58 bytes) in batch in a transparent way."""
        if not msg:
            raise Exception("Missing msg")

        # Split the payload in multiple chunks
        chunks = [payload[x:x+MAX_LARGE_PAYLOAD_SIZE-1] for x in range(0, len(payload), 57)]
        for chunk in chunks:
            current_payload = bytes([slot_id, key_type])

            # Append the actual payload
            if isinstance(chunk, list):
                current_payload += bytes(chunk)
            else:
                current_payload += chunk

        self.send_message(payload=current_payload, msg=msg)

    def read_bytes(self, n=64, to_str=False, timeout_ms=100):
        """Read n bytes and return an array of uint8 (int)."""
        out = self._hid.read(n, timeout=timeout_ms)
        if to_str:
            # Returns the bytes a string if requested
            return out.hex()

        # Returns the raw list
        return out

    def read_string(self, timeout_ms=100):
        """Read an ASCII string."""
        return self.read_chunk(timeout_ms=timeout_ms).decode("ascii")

    def read_chunk(self, timeout_ms=100):
        return self.read_bytes(MAX_INPUT_REPORT_SIZE, timeout_ms=timeout_ms)

    def getlabels(self):
        """Fetch the list of `Slot` from the OnlyKey.

        No need to read messages.
        """
        self.send_message(msg=Message.OKGETLABELS)
        time.sleep(0.5)
        slots = []
        for _ in range(12):
            data = self.read_string().split('|')
            slot_number = ord(data[0])
            if slot_number >= 16:
                slot_number = slot_number - 6
            if 1 <= slot_number <= 12:
                slots.append(Slot(slot_number, label=data[1]))
        return slots

    def getkeylabels(self):
        """Fetch the list of `Keys` from the OnlyKey.

        No need to read messages.
        """
        self.send_message(msg=Message.OKGETLABELS, slot_id=107)
        slots = []
        for _ in range(33):
            data = self.read_chunk()
            bef, _, aft = data.partition(b"|")
            slot_number = bef[0]
            if 25 <= slot_number <= 57:
                slots.append(Slot(slot_number, label=data[1]))

        return slots

    def displaykeylabels(self):
        global slot
        time.sleep(2)

        self.read_string(timeout_ms=100)
        empty = 'a'
        while not empty:
            empty = self.read_string(timeout_ms=100)

        time.sleep(1)
        print('You should see your OnlyKey blink 3 times\n')

        tmp = {}
        for slot in self.getkeylabels():
            tmp[slot.name] = slot
        slots = iter(['RSA Key 1', 'RSA Key 2', 'RSA Key 3', 'RSA Key 4', 'ECC Key 1', 'ECC Key 2', 'ECC Key 3', 'ECC Key 4', 'ECC Key 5', 'ECC Key 6', 'ECC Key 7', 'ECC Key 8', 'ECC Key 9', 'ECC Key 10', 'ECC Key 11', 'ECC Key 12', 'ECC Key 13', 'ECC Key 14', 'ECC Key 15', 'ECC Key 16', 'ECC Key 17', 'ECC Key 18', 'ECC Key 19', 'ECC Key 20', 'ECC Key 21', 'ECC Key 22', 'ECC Key 23', 'ECC Key 24', 'ECC Key 25', 'ECC Key 26', 'ECC Key 27', 'ECC Key 28', 'ECC Key 29'])
        for slot_name in slots:
            print(tmp[slot_name].to_str())

    def setslot(self, slot_number, message_field, value):
        """Set a slot field to the given value.
        """
        self.send_message(msg=Message.OKSETSLOT, slot_id=slot_number, message_field=message_field, payload=value)
        # Set U2F
        # [255, 255, 255, 255, 230, 12, 8, 117, 50, 102, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        print(self.read_string())

    def wipeslot(self, slot_number):
        """Wipe all the fields for the given slot."""
        self.send_message(msg=Message.OKWIPESLOT, slot_id=slot_number)
        for _ in range(8):
            print(self.read_string())

    def sign(self, SignatureHash):
        global slotnum
        print('Signature hash to send to OnlyKey= ', binascii.hexlify(SignatureHash))

        time.sleep(2)

        self.read_string(timeout_ms=100)
        empty = 'a'
        while not empty:
            empty = self.read_string(timeout_ms=100)

        time.sleep(1)
        print('You should see your OnlyKey blink 3 times\n')

        # Compute the challenge pin
        h = hashlib.sha256()
        h.update(SignatureHash)
        d = h.digest()

        assert len(d) == 32

        def get_button(byte):
            ibyte = ord(byte)
            if ibyte < 6:
                return 1
            return ibyte % 5 + 1

        b1, b2, b3 = get_button(d[0]), get_button(d[15]), get_button(d[31])

        print('Sending the payload to the OnlyKey...')
        self.send_large_message2(msg=Message.OKSIGNCHALLENGE, payload=SignatureHash, slot_id=slotnum)

        print('Please enter the 3 digit challenge code on OnlyKey (and press ENTER if necessary)')
        print('{} {} {}'.format(b1, b2, b3))
        input()
        print('Trying to read the signature from OnlyKey')
        print('For RSA with 4096 keysize this may take up to 9 seconds...')
        ok_sign1 = ''
        while ok_sign1 == '':
            time.sleep(0.5)
            ok_sign1= self.read_bytes(64, to_str=True)
            print(type(ok_sign1))

        print()
        print('received=', repr(ok_sign1))

        print('Trying to read the signature part 2...')
        for _ in range(10):
            ok_sign2 = self.read_bytes(64, to_str=True)
            if len(ok_sign2) == 64:
                break

        print()
        print('received=', repr(ok_sign2))

        print('Trying to read the signature part 3...')
        for _ in range(10):
            ok_sign3 = self.read_bytes(64, to_str=True)
            if len(ok_sign3) == 64:
                break


        print()
        print('received=', repr(ok_sign3))

        print('Trying to read the signature part 4...')
        for _ in range(10):
            ok_sign4 = self.read_bytes(64, to_str=True)
            if len(ok_sign4) == 64:
                break


        print()
        print('received=', repr(ok_sign4))

        print('Trying to read the signature part 5...')
        for _ in range(10):
            ok_sign5 = self.read_bytes(64, to_str=True)
            if len(ok_sign5) == 64:
                break


        print()
        print('received=', repr(ok_sign5))

        print('Trying to read the signature part 6...')
        for _ in range(10):
            ok_sign6 = self.read_bytes(64, to_str=True)
            if len(ok_sign6) == 64:
                break


        print()
        print('received=', repr(ok_sign6))

        print('Trying to read the signature part 7...')
        for _ in range(10):
            ok_sign7 = self.read_bytes(64, to_str=True)
            if len(ok_sign7) == 64:
                break


        print()
        print('received=', repr(ok_sign7))

        print('Trying to read the signature part 8...')
        for _ in range(10):
            ok_sign8 = self.read_bytes(64, to_str=True)
            if len(ok_sign8) == 64:
                break

        print()
        print('received=', repr(ok_sign8))

        if not ok_sign2:
            raise Exception('failed to read signature from OnlyKey')

        ok_signed = ok_sign1 + ok_sign2 + ok_sign3 + ok_sign4 + ok_sign5 + ok_sign6 + ok_sign7 + ok_sign8

        print('Signed by OnlyKey, data=', repr(ok_signed))
        print('Raw Signature= ', binascii.hexlify(ok_signed))

        return ok_signed

    def slot(self, slot):
        global slotnum
        slotnum = slot


    def getpub(self):
        global slotnum
        time.sleep(2)

        self.read_string(timeout_ms=100)
        empty = 'a'
        while not empty:
            empty = self.read_string(timeout_ms=100)

        time.sleep(1)
        print('You should see your OnlyKey blink 3 times')
        print()


        print('Trying to read the public RSA N part 1...')
        self.send_message(msg=Message.OKGETPUBKEY, payload=chr(slotnum))  #, payload=[1, 1])
        time.sleep(1)
        ok_pubkey1 = ''
        while ok_pubkey1 == '':
            time.sleep(0.5)
            ok_pubkey1= self.read_bytes(64)

        print()
        print('received=', repr(ok_pubkey1))

        print('Trying to read the public RSA N part 2...')
        for _ in range(10):
            ok_pubkey2 = self.read_bytes(64)
            if len(ok_pubkey2) == 64:
                break

        print()
        print('received=', repr(ok_pubkey2))

        print('Trying to read the public RSA N part 3...')
        for _ in range(10):
            ok_pubkey3 = self.read_bytes(64)
            if len(ok_pubkey3) == 64:
                break


        print()
        print('received=', repr(ok_pubkey3))

        print('Trying to read the public RSA N part 4...')
        for _ in range(10):
            ok_pubkey4 = self.read_bytes(64)
            if len(ok_pubkey4) == 64:
                break


        print()
        print('received=', repr(ok_pubkey4))

        print('Trying to read the public RSA N part 5...')
        for _ in range(10):
            ok_pubkey5 = self.read_bytes(64)
            if len(ok_pubkey5) == 64:
                break


        print()
        print('received=', repr(ok_pubkey5))

        print('Trying to read the public RSA N part 6...')
        for _ in range(10):
            ok_pubkey6 = self.read_bytes(64)
            if len(ok_pubkey6) == 64:
                break


        print()
        print('received=', repr(ok_pubkey6))

        print('Trying to read the public RSA N part 7...')
        for _ in range(10):
            ok_pubkey7 = self.read_bytes(64)
            if len(ok_pubkey7) == 64:
                break


        print()
        print('received=', repr(ok_pubkey7))
        print('Trying to read the public RSA N part 8...')

        for _ in range(10):
            ok_pubkey8 = self.read_bytes(64)
            if len(ok_pubkey8) == 64:
                break

        print()
        print('received=', repr(ok_pubkey8))

        if not ok_pubkey2:
            raise Exception('failed to read public RSA N from OnlyKey')


        print('Received Public Key generated by OnlyKey')
        ok_pubkey = ok_pubkey1 + ok_pubkey2 + ok_pubkey3 + ok_pubkey4 + ok_pubkey5 + ok_pubkey6 + ok_pubkey7 + ok_pubkey8
        print('Public N=', repr(ok_pubkey))
        print()

        print('Key Size =', len(ok_pubkey))
        print()

        return ok_pubkey

    def decrypt(self, ct):
        global slotnum
        time.sleep(2)

        self.read_string(timeout_ms=100)
        empty = 'a'
        while not empty:
            empty = self.read_string(timeout_ms=100)

        time.sleep(1)
        print('You should see your OnlyKey blink 3 times')
        print()

        # Compute the challenge pin
        h = hashlib.sha256()
        h.update(ct)
        d = h.digest()

        assert len(d) == 32

        def get_button(byte):
            ibyte = ord(byte)
            if ibyte < 6:
                return 1
            return ibyte % 5 + 1

        b1, b2, b3 = get_button(d[0]), get_button(d[15]), get_button(d[31])

        print('Sending the payload to the OnlyKey...')
        self.send_large_message2(msg=Message.OKDECRYPT, payload=ct, slot_id=slotnum)

        print('Please enter the 3 digit challenge code on OnlyKey (and press ENTER if necessary)')
        print('{} {} {}'.format(b1, b2, b3))
        input()
        print('Trying to read the decrypted data from OnlyKey')
        print('For RSA with 4096 keysize this may take up to 9 seconds...')
        ok_decrypted = ''
        while ok_decrypted == '':
            time.sleep(0.5)
            ok_decrypted = self.read_bytes(64, to_str=True)

        print('Decrypted by OnlyKey, data=', repr(ok_decrypted))

        return ok_decrypted

    def generate_backup_key(self):
        """ED25519 with backup flag"""
        print('WARNING - Only run this on a trusted device, save the backup key to a secure location, and then securely delete the backup key')
        ecc_type = 161
        default_slot = 132

        self.set_ecc_key(default_slot, ecc_type, chr(0))
        time.sleep(.5)

        log.info('Trying to read the private key...')
        for _ in range(2):
            ok_priv = self.read_bytes(64, to_str=True, timeout_ms=10)
            if len(ok_priv) == 64:
                break

        ok_priv = ok_priv[0:32]
        print('Store backup key in a secure location (i.e. USB drive in a safe)=', repr(ok_priv))
        print()
        ok_priv = 0;
