"""The project file both Actions read: simantic.json, the format the Simantic
PR reviewer reads too (cloud-sim review-image/worker/src/config.ts is its one
definition), or simantic.yml, the flat file this Action read before it.

  python3 simantic_config.py setup   what setup/action.yml installs, as step outputs
"""

import json
import os
import re
import subprocess
import sys

JSON_NAME = 'simantic.json'
YML_NAME = 'simantic.yml'

# The versions the PR reviewer's image has (review-image/Dockerfile
# ARM_GNU_VERSION and PICO_SDK_TAG), so CI and a review build alike.
DEFAULT_ARM_GNU = '14.3.rel1'
DEFAULT_PICO_SDK = '2.1.1'

# Unknown keys are an error, as in the reviewer's schema: a file one reads,
# the other must read the same way.
TOP_KEYS = {'$schema', 'name', 'mcu', 'build', 'toolchain', 'simulate'}
TOOLCHAIN_KEYS = {'arm-gnu', 'pico-sdk', 'zephyr', 'esp-idf'}
BUILD_SYSTEMS = {'cubemx-make', 'make', 'cmake', 'pico-sdk', 'esp-idf', 'zephyr'}
VERSION = re.compile(r'^v?\d[\w.-]{0,31}$')

PICO_SDK_REPO = 'https://github.com/raspberrypi/pico-sdk'


class ConfigError(Exception):
    pass


def find(path=''):
    """The config to read: `path` if given, else simantic.json in the
    working directory, else simantic.yml."""
    if path:
        if not os.path.isfile(path):
            raise ConfigError(f'config {path} does not exist')
        return path
    for name in (JSON_NAME, YML_NAME):
        if os.path.isfile(name):
            return name
    raise ConfigError(
        f'no {JSON_NAME} in the repository root: add one such as {{"mcu": "STM32F401RE"}}, '
        f'or pass config: <path> for a project in a subfolder')


def load(path=''):
    """{'path', 'mcu', 'build_system', 'toolchain', 'trigger', 'legacy'}.
    `trigger` is only ever set by a simantic.yml; simantic.json leaves when
    CI runs to the workflow's `on:`."""
    path = find(path)
    if path.endswith('.json'):
        return load_json(path)
    return load_yml(path)


def load_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except ValueError as e:
        raise ConfigError(f'{path} is not valid JSON: {e}')
    if not isinstance(data, dict):
        raise ConfigError(f'{path} must be a JSON object')
    unknown = sorted(set(data) - TOP_KEYS)
    if unknown:
        raise ConfigError(f'{path}: unknown key {", ".join(unknown)}')

    mcu = data.get('mcu')
    if not isinstance(mcu, str) or not mcu.strip():
        raise ConfigError(f'{path}: mcu is required, such as "STM32F401RE"')

    build = data.get('build', {})
    if not isinstance(build, dict):
        raise ConfigError(f'{path}: build must be an object')
    system = build.get('system')
    if system is not None and system not in BUILD_SYSTEMS:
        raise ConfigError(f'{path}: build.system must be one of {", ".join(sorted(BUILD_SYSTEMS))}')

    toolchain = data.get('toolchain', {})
    if not isinstance(toolchain, dict):
        raise ConfigError(f'{path}: toolchain must be an object')
    unknown = sorted(set(toolchain) - TOOLCHAIN_KEYS)
    if unknown:
        raise ConfigError(f'{path}: unknown toolchain {", ".join(unknown)}')
    for name, value in toolchain.items():
        if not isinstance(value, str) or not VERSION.match(value):
            raise ConfigError(f'{path}: toolchain.{name} must be a version, such as 14.3 or 2.1.1')

    return {'path': path, 'mcu': mcu.strip(), 'build_system': system,
            'toolchain': toolchain, 'trigger': None, 'legacy': False}


def load_yml(path):
    """simantic.yml was only ever flat `key: value` lines (mcu_model,
    build_system, trigger), so it is read as that and PyYAML isn't needed."""
    data = {}
    with open(path) as f:
        for n, line in enumerate(f, 1):
            line = line.split('#', 1)[0].rstrip()
            if not line.strip():
                continue
            key, sep, value = line.partition(':')
            if not sep or line[0].isspace():
                raise ConfigError(f'{path}:{n}: expected a flat "key: value" line; move to {JSON_NAME}')
            data[key.strip()] = value.strip().strip('\'"')

    mcu = data.get('mcu_model')
    if not mcu:
        raise ConfigError(f'{path}: missing required key: mcu_model')
    return {'path': path, 'mcu': mcu, 'build_system': None, 'toolchain': {},
            'trigger': data.get('trigger') or None, 'legacy': True}


def needed(cfg):
    """The toolchains the project builds with: the ones its toolchain names,
    else what its build system or MCU calls for. A pico-sdk build also needs
    the Arm compiler."""
    names = set(cfg['toolchain'])
    if not names:
        system = cfg['build_system']
        mcu = cfg['mcu'].upper()
        if system == 'pico-sdk' or mcu.startswith('RP2'):
            names = {'pico-sdk'}
        elif system in ('esp-idf', 'zephyr'):
            names = {system}
        elif mcu.startswith('STM32'):
            names = {'arm-gnu'}
        elif 'ESP32' in mcu:
            names = {'esp-idf'}
    if 'pico-sdk' in names:
        names.add('arm-gnu')
    return names


def arm_gnu_release(version):
    """An Arm GNU Toolchain release as developer.arm.com names it: 14.3 and
    14.3.rel1 are both 14.3.rel1."""
    v = version.removeprefix('v')
    if re.fullmatch(r'\d+\.\d+\.rel\d+', v):
        return v
    if re.fullmatch(r'\d+\.\d+', v):
        return f'{v}.rel1'
    raise ConfigError(f'toolchain.arm-gnu {version}: give a release such as 14.3 or 14.3.rel1')


def pico_sdk_tag(version, tags=None):
    """The newest pico-sdk release tag `version` is a prefix of (2.1 is
    2.1.1). `tags` is the repository's, listed from GitHub when not given."""
    v = version.removeprefix('v')
    if re.fullmatch(r'\d+\.\d+\.\d+', v):
        return v
    if tags is None:
        out = subprocess.run(['git', 'ls-remote', '--tags', '--refs', PICO_SDK_REPO],
                             capture_output=True, text=True, check=True).stdout
        tags = [line.rsplit('/', 1)[-1] for line in out.splitlines()]
    matching = [t for t in tags if re.fullmatch(r'\d+\.\d+\.\d+', t) and (t + '.').startswith(v + '.')]
    if not matching:
        raise ConfigError(f'toolchain.pico-sdk {version}: no pico-sdk release matches it')
    return max(matching, key=lambda t: tuple(int(p) for p in t.split('.')))


def setup_outputs(cfg, tags=None):
    """(outputs, notices): the versions setup/action.yml installs ('' for
    one it doesn't) and what to tell the user about the rest."""
    names = needed(cfg)
    tc = cfg['toolchain']
    outputs = {
        'mcu': cfg['mcu'],
        'arm_gnu': arm_gnu_release(tc['arm-gnu']) if 'arm-gnu' in tc else (DEFAULT_ARM_GNU if 'arm-gnu' in names else ''),
        'pico_sdk': pico_sdk_tag(tc['pico-sdk'], tags) if 'pico-sdk' in tc else (DEFAULT_PICO_SDK if 'pico-sdk' in names else ''),
    }
    notices = []
    if 'zephyr' in names:
        notices.append('Zephyr is not installed by this step: set it up before your build '
                       '(zephyrproject-rtos/action-zephyr)')
    if 'esp-idf' in names:
        notices.append('ESP-IDF is not installed by this step: build with espressif/esp-idf-ci-action')
    if not names:
        notices.append(f'no toolchain is known for {cfg["mcu"]}: name one in toolchain, or set it up yourself')
    return outputs, notices


def warn_legacy(cfg):
    if cfg['legacy']:
        print(f'::warning file={cfg["path"]}::{YML_NAME} is deprecated: replace it with {JSON_NAME} '
              f'({{"mcu": "{cfg["mcu"]}"}}), and choose when CI runs with the workflow\'s on:')


def main(argv):
    if argv[1:] != ['setup']:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        cfg = load(os.environ.get('CONFIG', ''))
        outputs, notices = setup_outputs(cfg)
    except (ConfigError, subprocess.CalledProcessError) as e:
        print(f'::error::{e}')
        return 1
    warn_legacy(cfg)
    for notice in notices:
        print(f'::notice::{notice}')
    print(f'{cfg["path"]}: mcu {cfg["mcu"]}, arm-gnu {outputs["arm_gnu"] or "-"}, pico-sdk {outputs["pico_sdk"] or "-"}')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        for key, value in outputs.items():
            f.write(f'{key}={value}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
