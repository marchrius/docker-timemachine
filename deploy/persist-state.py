#!/usr/bin/env python3
"""Initialize rupert's production state volume from the stopped qualified trial.

Run on the Pi only, after graceful client detach and explicit server stop.
Never copies live databases or touches the backup data filesystem.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import uuid

BASE = Path('/home/matteo/timemachine-trial-20261026')
SOURCE = 'timemachine-samba-trial'
SOURCE_ID = '5d5a77b19134302b0aa4251a5bd826fe493145ffb6453862a1fd2fd7378989fc'
VOLUME = 'timemachine_samba_state'
IMAGE = 'timemachine-samba:4.23.13-r0'


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()


def inventory(stream):
    result = {}
    with tarfile.open(fileobj=stream, mode='r:*') as archive:
        for member in archive:
            digest = hashlib.sha256(archive.extractfile(member).read()).hexdigest() if member.isfile() else None
            result[member.name.rstrip('/')] = (member.type, member.uid, member.gid,
                                               member.mode, member.linkname, digest)
    return result


def main():
    os.umask(0o077)
    assert BASE.is_dir() and BASE.stat().st_uid == os.getuid()
    assert BASE.stat().st_mode & 0o077 == 0
    source = json.loads(docker('inspect', SOURCE))[0]
    assert source['Id'] == SOURCE_ID and not source['State']['Running']
    original = json.loads(docker('inspect', 'timemachine-core-1'))[0]
    assert not original['State']['Running']
    image = json.loads(docker('image', 'inspect', IMAGE))[0]
    assert image['Id'] == source['Image']
    assert image['Architecture'] == 'arm64'
    assert image['Config']['Entrypoint'] == ['/entrypoint.sh']
    volumes = docker('volume', 'ls', '--format', '{{.Name}}').splitlines()
    assert VOLUME not in volumes, 'Refusing to overwrite an existing state volume'
    archive = BASE / 'qualified-trial-state.tar'
    with archive.open('xb') as output:
        subprocess.run(['docker', 'cp', '-a', f'{SOURCE}:/var/lib/samba', '-'],
                       stdout=output, check=True)
    docker('volume', 'create', VOLUME)
    helper = 'tm-state-import-' + uuid.uuid4().hex[:12]
    try:
        docker('create', '--name', helper, '--network', 'none', '--entrypoint', '/bin/true',
               '--mount', f'type=volume,src={VOLUME},dst=/var/lib/samba,volume-nocopy',
               image['Id'])
        with archive.open('rb') as source_tar:
            subprocess.run(['docker', 'cp', '-a', '-', f'{helper}:/var/lib'],
                           stdin=source_tar, check=True)
        copied = subprocess.check_output(['docker', 'cp', '-a', f'{helper}:/var/lib/samba', '-'])
        with archive.open('rb') as source_tar:
            assert inventory(source_tar) == inventory(io.BytesIO(copied))
        (BASE / 'persistent-state.json').write_text(json.dumps({
            'source_container': SOURCE_ID, 'image': image['Id'], 'volume': VOLUME,
            'offline_archive': str(archive), 'verified': True,
        }, indent=2) + '\n')
        print('PASS: qualified offline state imported into production volume; contents, ownership and modes match.')
    finally:
        docker('rm', helper)


if __name__ == '__main__':
    main()
