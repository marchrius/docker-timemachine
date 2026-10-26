#!/usr/bin/env python3
"""Discover signed patch releases and skip versions already published on GHCR."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

STABLE = 'https://download.samba.org/pub/samba/stable/'
API = 'https://api.github.com'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.names.update(value for key, value in attrs if key == 'href' and value)


def latest_release(index, series, minimum):
    if not re.fullmatch(r'\d+\.\d+', series):
        raise ValueError('Expected a major.minor series')
    if not re.fullmatch(re.escape(series) + r'\.\d+', minimum):
        raise ValueError('Minimum must be a patch in the selected series')
    parser = Links()
    parser.feed(index)
    versions = []
    for name in parser.names:
        match = re.fullmatch(r'samba-(' + re.escape(series) + r'\.\d+)\.tar\.gz', name)
        if match and name.removesuffix('.gz') + '.asc' in parser.names:
            versions.append(tuple(map(int, match[1].split('.'))))
    if not versions or max(versions) < tuple(map(int, minimum.split('.'))):
        raise ValueError('No signed release at or above the qualified minimum')
    return '.'.join(map(str, max(versions)))


def github_json(path, token):
    request = Request(API + path, headers={
        'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'timemachine-samba-release',
    })
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def is_published(repository, version, token, get_json=github_json, package=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid repository')
    if not token:
        raise ValueError('GH_TOKEN is required to check package versions')
    owner, repository_name = repository.lower().split('/')
    package = package or repository_name
    if not re.fullmatch(r'[a-z0-9_.-]+', package):
        raise ValueError('Invalid container package name')
    repo = get_json(f'/repos/{repository}', token)
    kind = 'orgs' if repo['owner']['type'] == 'Organization' else 'users'
    page = 1
    while True:
        try:
            versions = get_json(
                f'/{kind}/{owner}/packages/container/{package}/versions?per_page=100&page={page}', token)
        except HTTPError as error:
            # Only an absent package is the initial-publication case. Auth,
            # rate limits, outages and connection errors must fail the check.
            if error.code == 404 and page == 1:
                return False
            raise
        if any(version in item.get('metadata', {}).get('container', {}).get('tags', [])
               for item in versions):
            return True
        if len(versions) < 100:
            return False
        page += 1


def source_checksum(version):
    digest = hashlib.sha512()
    with urlopen(STABLE + f'samba-{version}.tar.gz', timeout=30) as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--discover-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(Path(__file__).with_name('samba-series.json').read_text())
    with urlopen(STABLE, timeout=30) as index:
        version = latest_release(index.read().decode(), config['series'], config['minimum_version'])
    if args.discover_only:
        print(version)
        return
    published = is_published(args.repository, version, os.environ.get('GH_TOKEN'),
                             package=config['package'])
    # Push/PR checks also build existing releases to validate code changes;
    # daily/manual checks compile only an unpublished patch.
    build = not published or os.environ.get('GITHUB_EVENT_NAME') in {'push', 'pull_request'}
    values = {
        'version': version,
        'image': f'ghcr.io/{args.repository.lower().split("/")[0]}/{config["package"]}',
        'build': str(build).lower(), 'publish': str(not published).lower(),
        'sha512': source_checksum(version) if build else '',
    }
    if output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a') as target:
            target.writelines(f'{key}={value}\n' for key, value in values.items())
    print(json.dumps(values, indent=2))


if __name__ == '__main__':
    main()
