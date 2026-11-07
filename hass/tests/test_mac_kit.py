"""HASS-MAC-KIT-1: the Mac mini kit (scripts and docs) is consistent, pinned and read-only where promised."""
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / 'scripts/hass/mac_setup_check.sh'
INSTALL = ROOT / 'scripts/hass/mac_install.sh'
STEPS = ROOT / 'docs/hass/MAC_MINI_FINAL_STEPS.md'
WIRING = ROOT / 'docs/hass/BRIDGE_WIRING.md'
# Pins recorded 2026-11-07 from the GitHub release page (BlueBubbles Server v1.9.12).
PINS = {
    'arm64': ('BlueBubbles-1.9.12-arm64-mac.zip', '296262790', 'e1d96d67fe4fc79ad44a8f1eeac3de78eef561635842b66d380dd3eba5092d89'),
    'x86_64': ('BlueBubbles-1.9.12-mac.zip', '302631985', '7078ea4302b4df6ab4b236bdaea84440aabf95b2a07b281919fd0ef8822e958c'),
}


def code_lines(path):
    return [l for l in path.read_text().splitlines() if l.strip() and not l.lstrip().startswith('#')]


class MacKitTests(unittest.TestCase):
    def test_scripts_parse_and_are_executable(self):
        for p in (CHECK, INSTALL):
            self.assertTrue(os.access(p, os.X_OK), p)
            r = subprocess.run(['bash', '-n', str(p)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_checker_changes_nothing(self):
        text = '\n'.join(code_lines(CHECK))
        for bad in (r'\bsudo\b', r'defaults\s+write', r'pmset\s+-a', r'launchctl\s+(bootstrap|load|kickstart|bootout)',
                    r'\brm\b', r'\bmv\b', r'\bkill', r'\btee\b', r'\btouch\b', r'\bmkdir\b', r'\bssh\b', r'\bcsrutil\b'):
            self.assertIsNone(re.search(bad, text), bad)
        for item in ('sw_vers', 'MobileMeAccounts', 'BlueBubbles', 'pgrep', 'tailscale', 'Tailscale', 'pmset -g', 'df -k'):
            self.assertIn(item, text)
        for word in ('PASS', 'FAIL', 'WARN'):
            self.assertIn(word, text)

    def test_installer_pins_match_and_print_before_download(self):
        for arch, (name, size, sha) in PINS.items():
            r = subprocess.run(['bash', str(INSTALL), '--print-plan'], capture_output=True, text=True,
                               env={**os.environ, 'MAC_INSTALL_ARCH': arch})
            self.assertEqual(r.returncode, 0, r.stderr)
            for want in (name, size, sha, '2026-10-27T23:04:07Z', 'pinned 2026-11-07'):
                self.assertIn(want, r.stdout)
        r = subprocess.run(['bash', str(INSTALL), '--print-plan'], capture_output=True, text=True,
                           env={**os.environ, 'MAC_INSTALL_ARCH': 'ppc'})
        self.assertEqual(r.returncode, 1)
        self.assertIn('REFUSED', r.stderr)

    def test_installer_verifies_before_install_and_needs_no_sudo(self):
        text = INSTALL.read_text()
        code = '\n'.join(code_lines(INSTALL))
        self.assertIsNone(re.search(r'\bsudo\b', code))
        self.assertIsNone(re.search(r'\b(ssh|csrutil|spctl|tccutil)\b', code))
        self.assertIn('https://github.com/${PIN_REPO}/releases/download/', text)
        self.assertLess(text.index('does not match the pin'), text.index('ditto -x -k'))
        self.assertLess(text.index('differs from the pinned'), text.index('curl -fL'))
        self.assertIn('com.avocadoshack.hass-bluebubbles', text)

    def test_docs_cover_steps_and_carry_no_values(self):
        steps = STEPS.read_text()
        for item in ('Apple Account', 'Remote Login', 'Full Disk Access', 'Automation', 'Private API', 'caffeinate',
                     'Total G time', 'UNVERIFIED', 'mac_install.sh', 'mac_setup_check.sh', 'Test plan'.lower()):
            self.assertIn(item.lower(), steps.lower())
        self.assertGreaterEqual(len(re.findall(r'^\d+\. \*\*', steps, re.M)), 10)
        wiring = WIRING.read_text()
        for key in ('ownerChat', 'receiverUrl', 'bbPort', 'bbPasswordFile', 'secretFile', 'spoolDir', 'webhookTokenFile',
                    'allowedPeers', '8795', 'loopback'):
            self.assertIn(key, wiring)
        for doc in (steps, wiring, INSTALL.read_text(), CHECK.read_text()):
            self.assertIsNone(re.search(r'\b[0-9a-f]{64}\b', doc.replace(PINS['arm64'][2], '').replace(PINS['x86_64'][2], '')))
            self.assertIsNone(re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', doc.replace('127.0.0.1', '').replace('100.64.0.0', '')))
            self.assertIsNone(re.search(r'BEGIN [A-Z ]*PRIVATE KEY|ssh-(rsa|ed25519) AAAA', doc))


if __name__ == '__main__':
    unittest.main()
