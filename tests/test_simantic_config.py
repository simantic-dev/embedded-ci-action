import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from simantic_config import (  # noqa: E402
    DEFAULT_ARM_GNU, DEFAULT_PICO_SDK, ConfigError, arm_gnu_release, load,
    pico_sdk_tag, setup_outputs,
)

PICO_TAGS = ['1.5.1', '2.0.0', '2.1.0', '2.1.0-correct-picotool', '2.1.1', '2.1.1-correct-picotool', '2.2.0']


class InDir(unittest.TestCase):
    """Each test runs in an empty directory, as a checkout's root."""

    def setUp(self):
        self._old = os.getcwd()
        self._dir = tempfile.TemporaryDirectory()
        os.chdir(self._dir.name)

    def tearDown(self):
        os.chdir(self._old)
        self._dir.cleanup()

    def write(self, name, text):
        os.makedirs(os.path.dirname(name) or '.', exist_ok=True)
        with open(name, 'w') as f:
            f.write(text if isinstance(text, str) else json.dumps(text))


class LoadTests(InDir):
    def test_json(self):
        self.write('simantic.json', {'mcu': ' STM32F401RE ', 'toolchain': {'arm-gnu': '14.2'}})
        cfg = load()
        self.assertEqual(cfg['mcu'], 'STM32F401RE')
        self.assertEqual(cfg['toolchain'], {'arm-gnu': '14.2'})
        self.assertIsNone(cfg['trigger'])
        self.assertFalse(cfg['legacy'])

    def test_json_wins_over_yml(self):
        self.write('simantic.json', {'mcu': 'RP2040'})
        self.write('simantic.yml', 'mcu_model: STM32F401RE\n')
        self.assertEqual(load()['mcu'], 'RP2040')

    def test_explicit_path(self):
        self.write('fw/simantic.json', {'mcu': 'RP2040'})
        self.assertEqual(load('fw/simantic.json')['mcu'], 'RP2040')
        with self.assertRaisesRegex(ConfigError, 'does not exist'):
            load('nope/simantic.json')

    def test_neither_file(self):
        with self.assertRaisesRegex(ConfigError, 'no simantic.json'):
            load()

    def test_json_errors(self):
        cases = [
            ('{', 'not valid JSON'),
            ('[]', 'must be a JSON object'),
            ({}, 'mcu is required'),
            ({'mcu': 'RP2040', 'trigger': 'push'}, 'unknown key trigger'),
            ({'mcu': 'RP2040', 'toolchain': {'gcc': '14'}}, 'unknown toolchain gcc'),
            ({'mcu': 'RP2040', 'toolchain': {'arm-gnu': 14.3}}, 'must be a version'),
            ({'mcu': 'RP2040', 'build': {'system': 'scons'}}, 'build.system'),
        ]
        for text, message in cases:
            with self.subTest(text=text):
                self.write('simantic.json', text)
                with self.assertRaisesRegex(ConfigError, message):
                    load()

    def test_yml(self):
        self.write('simantic.yml', "build_system: make\nmcu_model: 'STM32F401RE'  # the Nucleo\n\ntrigger: pull_request\n")
        cfg = load()
        self.assertEqual(cfg['mcu'], 'STM32F401RE')
        self.assertEqual(cfg['trigger'], 'pull_request')
        self.assertTrue(cfg['legacy'])

    def test_yml_without_trailing_newline(self):
        # ec2-test's simantic.yml ends without one.
        self.write('simantic.yml', 'build_system: build\nmcu_model: STM32F401RE')
        self.assertEqual(load()['mcu'], 'STM32F401RE')

    def test_yml_errors(self):
        self.write('simantic.yml', 'build_system: make\n')
        with self.assertRaisesRegex(ConfigError, 'mcu_model'):
            load()
        self.write('simantic.yml', 'mcu_model: RP2040\nsimulate:\n  seconds: 5\n')
        with self.assertRaisesRegex(ConfigError, 'flat'):
            load()


class SetupTests(InDir):
    def outputs(self, config):
        self.write('simantic.json', config)
        return setup_outputs(load(), tags=PICO_TAGS)

    def test_stm32_gets_arm(self):
        out, notices = self.outputs({'mcu': 'STM32F401RE'})
        self.assertEqual(out, {'mcu': 'STM32F401RE', 'arm_gnu': DEFAULT_ARM_GNU, 'pico_sdk': ''})
        self.assertEqual(notices, [])

    def test_rp2040_gets_arm_and_pico(self):
        out, _ = self.outputs({'mcu': 'RP2040'})
        self.assertEqual((out['arm_gnu'], out['pico_sdk']), (DEFAULT_ARM_GNU, DEFAULT_PICO_SDK))

    def test_build_system_decides_before_mcu(self):
        out, _ = self.outputs({'mcu': 'STM32F401RE', 'build': {'system': 'zephyr'}})
        self.assertEqual((out['arm_gnu'], out['pico_sdk']), ('', ''))

    def test_named_versions(self):
        out, _ = self.outputs({'mcu': 'RP2040', 'toolchain': {'arm-gnu': '13.3', 'pico-sdk': '2.1'}})
        self.assertEqual((out['arm_gnu'], out['pico_sdk']), ('13.3.rel1', '2.1.1'))

    def test_named_pico_brings_arm(self):
        out, _ = self.outputs({'mcu': 'RP2040', 'toolchain': {'pico-sdk': '2.0.0'}})
        self.assertEqual((out['arm_gnu'], out['pico_sdk']), (DEFAULT_ARM_GNU, '2.0.0'))

    def test_named_toolchain_overrides_inference(self):
        # An STM32 built with Zephyr's own SDK needs no Arm GNU install.
        out, notices = self.outputs({'mcu': 'STM32F401RE', 'toolchain': {'zephyr': '4.4'}})
        self.assertEqual(out['arm_gnu'], '')
        self.assertIn('Zephyr', notices[0])

    def test_esp32_gets_a_notice(self):
        out, notices = self.outputs({'mcu': 'ESP32-C3'})
        self.assertEqual((out['arm_gnu'], out['pico_sdk']), ('', ''))
        self.assertIn('esp-idf-ci-action', notices[0])

    def test_unknown_mcu_gets_a_notice(self):
        _, notices = self.outputs({'mcu': 'ATSAMD21G18'})
        self.assertIn('no toolchain is known', notices[0])


class VersionTests(unittest.TestCase):
    def test_arm_gnu(self):
        self.assertEqual(arm_gnu_release('14.3'), '14.3.rel1')
        self.assertEqual(arm_gnu_release('v14.3.rel1'), '14.3.rel1')
        self.assertEqual(arm_gnu_release('13.2.rel1'), '13.2.rel1')
        for bad in ('14', '14.3.1', 'latest'):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                arm_gnu_release(bad)

    def test_pico_sdk(self):
        self.assertEqual(pico_sdk_tag('2.1.1', tags=[]), '2.1.1')
        self.assertEqual(pico_sdk_tag('2.1', PICO_TAGS), '2.1.1')
        self.assertEqual(pico_sdk_tag('v2', PICO_TAGS), '2.2.0')
        self.assertEqual(pico_sdk_tag('1', PICO_TAGS), '1.5.1')
        with self.assertRaises(ConfigError):
            pico_sdk_tag('3', PICO_TAGS)
        # A prefix matches whole parts: 2.1 is not 2.10.
        self.assertEqual(pico_sdk_tag('2.1', ['2.1.0', '2.10.0']), '2.1.0')


if __name__ == '__main__':
    unittest.main()
