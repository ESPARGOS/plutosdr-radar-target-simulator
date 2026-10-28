"""Check firmware extraction rejects malformed headers and invalid FRM checksums."""
import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from import_base_firmware import extract


class FirmwareImportTests(unittest.TestCase):
    def setUp(self):
        self.fit = bytearray(128)
        struct.pack_into('>II', self.fit, 0, 0xd00dfeed, len(self.fit))
        self.fit[40:40+len(b'ITB PlutoSDR (ADALM-PLUTO)')] = b'ITB PlutoSDR (ADALM-PLUTO)'
        self.fit = bytes(self.fit)

    def test_fit_and_partition(self):
        self.assertEqual(extract(self.fit), self.fit)
        self.assertEqual(extract(self.fit+b'\xff'*128), self.fit)

    def test_frm_checksum(self):
        checksum = hashlib.md5(self.fit).hexdigest().encode()+b'\n'
        self.assertEqual(extract(self.fit+checksum), self.fit)
        with self.assertRaises(ValueError):
            extract(self.fit+b'0'*32+b'\n')

    def test_invalid_headers(self):
        for invalid in (b'', b'not firmware'*20, self.fit[:-1], self.fit[:40]+b'\0'*88):
            with self.subTest(data=invalid[:8]), self.assertRaises(ValueError):
                extract(invalid)


if __name__ == '__main__':
    unittest.main()
