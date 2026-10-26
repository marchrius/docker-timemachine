from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib.error import HTTPError

from samba_release import is_published, latest_release

ROOT = Path(__file__).resolve().parents[1]


def index(*versions):
    return ''.join(f'<a href="samba-{v}.tar.gz">tar</a><a href="samba-{v}.tar.asc">sig</a>'
                   for v in versions)


class Releases(unittest.TestCase):
    def http_error(self, path, code):
        error = HTTPError(path, code, 'Failed', {}, None)
        self.addCleanup(error.close)
        return error

    def test_numeric_sort_and_patch_only(self):
        self.assertEqual(latest_release(index('4.23.9', '4.23.13', '4.23.14rc1',
                                              '4.24.99', '4.230.99'), '4.23', '4.23.13'), '4.23.13')

    def test_new_patch(self):
        self.assertEqual(latest_release(index('4.23.13', '4.23.14'), '4.23', '4.23.13'), '4.23.14')

    def test_unsigned_and_foreign_links_ignored(self):
        html = index('4.23.13') + '<a href="samba-4.23.99.tar.gz">unsigned</a>'
        html += '<a href="https://evil.invalid/samba-4.23.100.tar.gz">external</a>'
        self.assertEqual(latest_release(html, '4.23', '4.23.13'), '4.23.13')

    def test_empty_or_downgraded_listing_fails(self):
        for html in ('', index('4.23.12'), index('4.24.1')):
            with self.subTest(html=html), self.assertRaises(ValueError):
                latest_release(html, '4.23', '4.23.13')

    def test_missing_package_bootstraps(self):
        def get(path, token):
            if path.startswith('/repos/'):
                return {'owner': {'type': 'User'}}
            raise self.http_error(path, 404)
        self.assertFalse(is_published('owner/repo', '4.23.13', 'fake', get))

    def test_auth_and_network_errors_fail(self):
        for code in (401, 403, 429, 500):
            def get(path, token):
                if path.startswith('/repos/'):
                    return {'owner': {'type': 'User'}}
                raise self.http_error(path, code)
            with self.subTest(code=code), self.assertRaises(HTTPError):
                is_published('owner/repo', '4.23.13', 'fake', get)

    def test_tag_lookup_paginates_and_handles_org(self):
        seen = []
        def get(path, token):
            seen.append(path)
            if path.startswith('/repos/'):
                return {'owner': {'type': 'Organization'}}
            if path.endswith('&page=1'):
                return [{'metadata': {'container': {'tags': ['4.23.12']}}}] * 100
            return [{'metadata': {'container': {'tags': ['4.23.13']}}}]
        self.assertTrue(is_published('Owner/Repo', '4.23.13', 'fake', get))
        self.assertIn('/orgs/owner/packages/container/repo/versions?per_page=100&page=2', seen)

    def test_existing_package_without_patch(self):
        def get(path, token):
            return {'owner': {'type': 'User'}} if path.startswith('/repos/') else []
        self.assertFalse(is_published('owner/repo', '4.23.13', 'fake', get))


@unittest.skipUnless(shutil.which('sha512sum') and shutil.which('sed'), 'GNU/Alpine tools required')
class Packaging(unittest.TestCase):
    def prepare(self, version, checksum='a' * 128, corrupt_patch=False):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        recipe = root / 'APKBUILD'
        recipe.write_bytes((ROOT / 'lab/vendor/alpine-samba/APKBUILD').read_bytes())
        source = root / 'source'
        source.mkdir()
        (source / 'version').write_text(version + '\n')
        (source / 'source.sha512').write_text(f'{checksum}  samba-{version}.tar.gz\n')
        adaptations = root / 'adaptations'
        adaptations.mkdir()
        patch = ROOT / 'lab/patches/musl_uintptr.patch'
        (adaptations / patch.name).write_bytes(b'corrupt' if corrupt_patch else patch.read_bytes())
        result = subprocess.run(['sh', str(ROOT / 'lab/prepare-packages.sh'), str(recipe),
                                 str(source), str(adaptations)], capture_output=True, text=True)
        return result, recipe.read_text()

    def test_current_and_next_patch_preserve_other_checksums(self):
        original = (ROOT / 'lab/vendor/alpine-samba/APKBUILD').read_text()
        other_sums = [line for line in original.splitlines()
                      if len(line.split('  ', 1)[0]) == 128 and
                      'samba-4.23.8.tar.gz' not in line and 'musl_uintptr.patch' not in line]
        for version in ('4.23.13', '4.23.14'):
            with self.subTest(version=version):
                result, recipe = self.prepare(version)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'pkgver={version}\n', recipe)
                self.assertIn(f'{"a" * 128}  samba-{version}.tar.gz', recipe)
                self.assertTrue(all(line in recipe for line in other_sums))

    def test_unsupported_version_bad_checksum_and_patch_are_rejected(self):
        for version, checksum, corrupt in (('4.24.0', 'a' * 128, False),
                                          ('4.23.14rc1', 'a' * 128, False),
                                          ('4.23.14', 'invalid', False),
                                          ('4.23.14', 'a' * 128, True)):
            with self.subTest(version=version, checksum=checksum, corrupt=corrupt):
                result, _ = self.prepare(version, checksum, corrupt)
                self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
