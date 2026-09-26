#!/usr/bin/env python3
"""Native adapter regression checks. Set INSTALLER_INNOEXTRACT and INSTALLER_INNO_NEWER_FIXTURE."""
import os
import pathlib
import struct
import subprocess
import tempfile
import unittest
import zlib

from verify_inno import stream


@unittest.skipUnless(os.getenv('INSTALLER_INNOEXTRACT') and os.getenv('INSTALLER_INNO_NEWER_FIXTURE'),
                     'A built decoder and a public revision-2 fixture are required')
class StreamTests(unittest.TestCase):
    def setUp(self):
        self.tool = os.environ['INSTALLER_INNOEXTRACT']
        self.source = pathlib.Path(os.environ['INSTALLER_INNO_NEWER_FIXTURE']).resolve()
        self.data = bytearray(self.source.read_bytes())
        magic = bytes.fromhex('72446c507453cde6d77b0b2a')
        self.loader = self.data.find(magic)
        self.assertGreaterEqual(self.loader, 0)
        self.assertEqual(struct.unpack_from('<I', self.data, self.loader + 12)[0], 2)
        self.assertEqual(zlib.crc32(self.data[self.loader:self.loader + 60]),
                         struct.unpack_from('<I', self.data, self.loader + 60)[0])
        self.header, self.payload = struct.unpack_from('<QQ', self.data, self.loader + 40)
        self.encryption = self.header + 64

    def refused(self, data, diagnostic):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / 'modified.exe'
            source.write_bytes(data)
            result, files = stream(self.tool, source)
        self.assertNotEqual(result['exit_code'], 0, result)
        self.assertFalse(files, result)
        self.assertIn(diagnostic, result['stderr'])

    def test_encrypted_flag_cannot_be_discarded(self):
        self.data[self.encryption + 4] = 1
        crc = zlib.crc32(self.data[self.encryption + 4:self.encryption + 53])
        struct.pack_into('<I', self.data, self.encryption, crc)
        self.refused(self.data, 'Encrypted installers are unsupported')

    def test_corrupt_encryption_header_is_rejected(self):
        self.data[self.encryption] ^= 1
        self.refused(self.data, 'Encryption header checksum mismatch')

    def test_unknown_setup_version_is_rejected(self):
        self.assertEqual(self.data[self.header:self.header + 22], b'Inno Setup Setup Data ')
        self.data[self.header + 23] = ord('9')
        self.refused(self.data, 'Unexpected setup data version')

    def test_missing_external_slice_is_rejected(self):
        struct.pack_into('<Q', self.data, self.loader + 48, 0)
        struct.pack_into('<I', self.data, self.loader + 60,
                         zlib.crc32(self.data[self.loader:self.loader + 60]))
        self.refused(self.data, 'Missing external Inno data slice')

    def test_truncated_payload_cannot_publish_a_file(self):
        self.refused(self.data[:self.payload + 32], 'error')

    def test_stream_mode_rejects_other_actions_without_writing(self):
        for option in ['--extract', '--gog', '--dump-headers', '--list', '--list-checksums',
                       '--info', '--data-version', '--show-password']:
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run([self.tool, '--decompiler-stream', option, '--', str(self.source)],
                                        cwd=directory, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                # Release builds do not expose the debug-only --dump-headers option.
                if option == '--dump-headers' and b'unrecognised option' in result.stderr:
                    self.assertNotIn(b'IEX1\n', result.stdout)
                else:
                    self.assertEqual(result.stdout, b'')
                    self.assertIn(b'Incompatible stream options', result.stderr)
                self.assertEqual(list(pathlib.Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
