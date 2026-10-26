#!/usr/bin/env python3
"""Explicit preparation steps for the authorized rupert trial; run on the Pi.

No phase stops, starts or disconnects the original service. Those operations
remain separate commands so the operator can inspect each result.
Private artifacts never belong in the repository.
"""
import json
import hashlib
import http.client
import io
import os
from pathlib import Path
import subprocess
import sys
import socket
import tarfile

BASE = Path('/home/matteo/timemachine-trial-20261026')
OLD = 'timemachine-core-1'
NEW = 'timemachine-samba-trial'
EXPECTED_OLD = '34f6fe971983a713962ab8206e9649c666692872a26842c87799bdde88f7859b'
IMAGE = 'timemachine-samba:trial-4.23.13'


def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True)
    if result.returncode:
        # Do not echo arguments or environment (may contain credentials).
        raise RuntimeError(result.stderr)
    return result.stdout


def inspect(name):
    return json.loads(docker('inspect', name))[0]


def connect_endpoint(network, container, endpoint):
    class DockerSocket(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.connect('/var/run/docker.sock')

    connection = DockerSocket('localhost')
    payload = {'Container': container, 'EndpointConfig': endpoint}
    connection.request('POST', f'/networks/{network}/connect',
                       json.dumps(payload), {'Content-Type': 'application/json'})
    response = connection.getresponse()
    assert response.status == 200, response.read().decode()
    connection.close()


def main(phase):
    os.umask(0o077)
    assert BASE.is_dir() and BASE.stat().st_uid == os.getuid()
    assert BASE.stat().st_mode & 0o077 == 0
    old = inspect(OLD)
    assert old['Id'] == EXPECTED_OLD
    if phase == 'prepare':
        assert not (BASE / 'original.json').exists()
        assert old['State']['Running']
        assert {m['Destination']: m['Source'] for m in old['Mounts']} == {
            '/opt': '/mnt/timemachine', '/users': '/home/matteo/timemachine/users'}
        env = dict(e.split('=', 1) for e in old['Config']['Env'])
        assert all('\n' not in e and '\r' not in e for e in old['Config']['Env'])
        assert env['EXTERNAL_CONF'] == '/users'
        assert env['SET_PERMISSIONS'] == 'false'
        (BASE / 'original.json').write_text(json.dumps(old, indent=2))
        (BASE / 'original.env').write_text('\n'.join(old['Config']['Env']) + '\n')
        docker('cp', f'{OLD}:/users', str(BASE / 'users'))
        for source, destination in (('/etc/samba/smb.conf', 'smb.conf'),
                                    ('/etc/avahi', 'avahi'),
                                    ('/entrypoint.sh', 'original-entrypoint.sh')):
            docker('cp', f'{OLD}:{source}', str(BASE / destination))
        (BASE / 'original.sid').write_text(docker('exec', OLD, 'net', 'getlocalsid'))
        (BASE / 'original.accounts').write_text(docker('exec', OLD, 'pdbedit', '-L'))
        (BASE / 'original.testparm').write_text(docker('exec', OLD, 'testparm', '-s'))
        print('Prepared private configuration and identity; original service unchanged.')
    elif phase == 'export-state':
        assert not old['State']['Running']
        with (BASE / 'state.tar').open('xb') as output:
            subprocess.run(['docker', 'cp', '-a', f'{OLD}:/var/lib/samba', '-'],
                           stdout=output, check=True)
        print('Archived offline Samba state; original container retained.')
    elif phase == 'create':
        assert not old['State']['Running']
        assert 'timemachine_lan' not in old['NetworkSettings']['Networks']
        saved = json.loads((BASE / 'original.json').read_text())
        network = saved['NetworkSettings']['Networks']['timemachine_lan']
        assert network['IPAddress'] == '192.168.3.54'
        assert network['MacAddress'] == '02:42:c0:a8:03:36'
        image = json.loads(docker('image', 'inspect', IMAGE))[0]
        assert image['Architecture'] == 'arm64'
        assert image['Config']['Entrypoint'] == ['/entrypoint.sh']
        assert (BASE / 'state.tar').is_file()
        args = ['create', '--name', NEW, '--hostname', saved['Config']['Hostname'],
                '--restart', 'no', '--env-file', str(BASE / 'original.env'),
                '--network', 'name=timemachine_lan,ip=192.168.3.54,mac-address=02:42:c0:a8:03:36,alias=core,alias=timemachine-core-1',
                '--mount', 'type=bind,src=/mnt/timemachine,dst=/opt',
                '--mount', f'type=bind,src={BASE}/users,dst=/users,readonly',
                '--tmpfs', '/run/samba', image['Id']]
        print(docker(*args).strip())
        candidate = inspect(NEW)
        endpoint = candidate['NetworkSettings']['Networks']['timemachine_lan']
        # Static network values are also checked after start, when populated.
        assert endpoint['IPAMConfig']['IPv4Address'] == '192.168.3.54'
        (BASE / 'candidate.json').write_text(json.dumps(candidate, indent=2))
        print('Candidate created but NOT started; import offline state next.')
    elif phase == 'import-state':
        assert not old['State']['Running']
        assert not inspect(NEW)['State']['Running']
        with (BASE / 'state.tar').open('rb') as source:
            subprocess.run(['docker', 'cp', '-a', '-', f'{NEW}:/var/lib'],
                           stdin=source, check=True)

        def inventory(archive):
            result = {}
            with tarfile.open(fileobj=archive, mode='r:*') as tar:
                for member in tar:
                    digest = hashlib.sha256(tar.extractfile(member).read()).hexdigest() if member.isfile() else None
                    result[member.name.rstrip('/')] = (member.type, member.uid, member.gid,
                                                       member.mode, member.linkname, digest)
            return result

        actual = subprocess.check_output(['docker', 'cp', '-a', f'{NEW}:/var/lib/samba', '-'])
        with (BASE / 'state.tar').open('rb') as source:
            assert inventory(source) == inventory(io.BytesIO(actual))
        print('PASS: imported offline state, file contents/ownership/modes identical before boot.')
    elif phase == 'restore-network':
        assert not old['State']['Running']
        trial = inspect(NEW)
        assert not trial['State']['Running']
        assert 'timemachine_lan' not in trial['NetworkSettings']['Networks']
        assert 'timemachine_lan' not in old['NetworkSettings']['Networks']
        saved = json.loads((BASE / 'original.json').read_text())
        endpoint = saved['NetworkSettings']['Networks']['timemachine_lan']

        connect_endpoint('timemachine_lan', OLD, {
            'IPAMConfig': {'IPv4Address': endpoint['IPAddress']},
            'MacAddress': endpoint['MacAddress'], 'Aliases': endpoint['Aliases']})
        print('Original network reconnected; original container NOT started.')
    elif phase == 'test-network-api':
        import ipaddress
        import uuid
        name = 'tm-rollback-network-test-' + uuid.uuid4().hex[:12]
        try:
            docker('network', 'create', '--internal', name)
            network = json.loads(docker('network', 'inspect', name))[0]
            address = str(ipaddress.ip_network(network['IPAM']['Config'][0]['Subnet'])[10])
            mac = '02:42:ac:fe:00:0a'
            docker('run', '-d', '--name', name, '--network', 'none',
                   '--entrypoint', '/bin/sleep', IMAGE, '60')
            docker('network', 'disconnect', 'none', name)
            connect_endpoint(name, name, {'IPAMConfig': {'IPv4Address': address},
                                         'MacAddress': mac, 'Aliases': ['rollback-test']})
            endpoint = inspect(name)['NetworkSettings']['Networks'][name]
            assert endpoint['IPAddress'] == address
            assert endpoint['MacAddress'] == mac
            assert 'rollback-test' in endpoint['Aliases']
            print('PASS: rollback network API preserves IP/MAC/alias on disposable internal network.')
        finally:
            docker('rm', '-f', name)
            docker('network', 'rm', name)
    else:
        raise ValueError('Unknown explicit preparation phase')


if __name__ == '__main__':
    main(sys.argv[1])
