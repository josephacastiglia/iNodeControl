"""Read notices from verified source archives. Never execute PKGBUILD, hooks or source code."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from urllib.parse import urlsplit

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
import runtime_package_provenance as p

sources = repo / 'output/provenance/native-sources-20261012'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
assert out.is_relative_to(repo / 'output/provenance'), 'Output must be an evidence child'
out.mkdir(exist_ok=False)
tar = Path('C:/Windows/System32/tar.exe')
rows = []


def notice_name(name):
    return name.rsplit('/', 1)[-1].split('.', 1)[0].upper() in {'COPYING', 'COPYRIGHT', 'LICENSE', 'LICENCE', 'NOTICE'}


def save_notice(folder, name, data, origin, notices):
    if len(data) > 2 * 1024 * 1024 or b'\0' in data:
        raise ValueError('Notice is too large or binary: ' + name)
    data.decode('utf-8')  # Do not silently replace undecodable copyright bytes.
    target = p.runtime.package.safe(folder, 'notices/' + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream: stream.write(data)
    notices.append({'file': target.relative_to(out).as_posix(), 'member': name, 'sha256': p.sha(data), 'bytes': len(data), **origin})


def git_read(folder, args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    return subprocess.run(['git', '--no-pager', '-c', f'safe.directory={folder.as_posix()}',
        '--git-dir=' + str(folder), *args], env=env, capture_output=True, check=True, timeout=60).stdout


for source in json.loads((sources / 'source-provenance.json').read_text(encoding='utf-8'))['sources']:
    row = {**source, 'notice_state': 'unverified', 'notices': []}
    folder = out / (source['base'] + '-' + source['version'])
    folder.mkdir()
    try:
        assert source['state'] == 'signature_and_recipe_verified'
        origin = sources / folder.name
        archive = origin / (folder.name + '.src.tar.zst')
        assert p.sha(archive.read_bytes()) == source['archive_sha256']
        recipe = (origin / 'PKGBUILD').read_bytes()
        assert p.sha(recipe) == source['expected_recipe_sha256']
        srcinfo = p.read_member(archive, source['base'] + '/.SRCINFO', tar, p.run, 2 * 1024 * 1024)
        (folder / 'SRCINFO').write_bytes(srcinfo)
        # Keep the trailing separator for legal empty values such as "depends = ".
        info = p.metadata('\n'.join(line.lstrip() for line in srcinfo.decode('utf-8').splitlines()).encode())
        declared = info.get('source', [])
        algorithms = [(alg, info[alg + 'sums']) for alg in ('sha256', 'sha512', 'b2') if alg + 'sums' in info]
        if not algorithms or any(len(sums) != len(declared) for _, sums in algorithms):
            raise ValueError('Unrecognized or incomplete source checksum lists')
        members = (origin / 'archive-members.txt').read_text(encoding='utf-8').splitlines()
        for index, entry in enumerate(declared):
            alias, separator, url = entry.partition('::')
            if not separator: url = alias; alias = urlsplit(url).path.rsplit('/', 1)[-1]
            if url.startswith('git+'):
                # Import only signed object files into a fresh, inert bare object
                # database. Never read the archive's Git config or install hooks.
                gitdir = folder / ('objects-' + alias)
                (gitdir / 'objects/pack').mkdir(parents=True)
                (gitdir / 'refs').mkdir()
                (gitdir / 'config').write_text('[core]\nrepositoryformatversion = 0\nbare = true\n', encoding='utf-8')
                (gitdir / 'HEAD').write_text('ref: refs/heads/unborn\n', encoding='ascii')
                prefix = source['base'] + '/' + alias + '/'
                for member in members:
                    relative = member[len(prefix):] if member.startswith(prefix) else ''
                    if not re.fullmatch(r'objects/(?:pack/pack-[0-9a-f]+\.(?:pack|idx|rev)|[0-9a-f]{2}/[0-9a-f]{38})', relative): continue
                    payload = p.read_member(archive, member, tar, p.run)
                    target = p.runtime.package.safe(gitdir, relative)
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(payload)
                pin = urlsplit(url).fragment
                if pin.startswith('commit=') and re.fullmatch(r'[0-9a-f]{40}', pin[7:]):
                    object_id = pin[7:]
                    if object_id.encode() not in recipe: raise ValueError('Commit pin absent from matched build recipe')
                elif pin.startswith('tag='):
                    tag = pin[4:]
                    if not re.fullmatch(r'[A-Za-z0-9._+-]+', tag): raise ValueError('Unsafe source tag')
                    packed = p.read_member(archive, prefix + 'packed-refs', tar, p.run, 2 * 1024 * 1024).decode('utf-8')
                    matches = [line.split()[0] for line in packed.splitlines() if line.endswith(' refs/tags/' + tag)]
                    if len(matches) != 1 or not re.fullmatch(r'[0-9a-f]{40}', matches[0]): raise ValueError('No unique signed source tag')
                    object_id = matches[0]
                else: raise ValueError('Git source is not pinned to a commit or tag')
                commit = git_read(gitdir, ['rev-parse', '--verify', object_id + '^{commit}']).decode().strip()
                entries = git_read(gitdir, ['ls-tree', '-r', '-z', commit]).split(b'\0')
                for entry in entries:
                    if not entry: continue
                    header, name = entry.split(b'\t', 1); mode, kind, blob = header.split()
                    name = name.decode('utf-8')
                    if mode not in (b'100644', b'100755') or kind != b'blob' or not notice_name(name): continue
                    data = git_read(gitdir, ['cat-file', 'blob', blob.decode()])
                    save_notice(folder, alias + '/' + name, data, {'source_kind': 'signed_git_objects', 'source_pin': pin, 'resolved_commit': commit}, row['notices'])
                continue
            member = source['base'] + '/' + alias
            if not any(alias.endswith(suffix) for suffix in ('.tar.gz', '.tar.xz', '.tar.bz2', '.tgz')): continue
            payload = p.read_member(archive, member, tar, p.run)
            for algorithm, sums in algorithms:
                expected = sums[index]
                if expected == 'SKIP': raise ValueError('Archive source lacks a content checksum')
                calculated = hashlib.new('blake2b' if algorithm == 'b2' else algorithm, payload).hexdigest()
                if calculated != expected or expected.encode() not in recipe:
                    raise ValueError('Nested source checksum does not match the recorded build recipe')
            nested_sha = p.sha(payload)
            with tarfile.open(fileobj=io.BytesIO(payload), mode='r:*') as nested:
                for member_info in nested:
                    if not member_info.isfile() or not notice_name(member_info.name): continue
                    if member_info.size > 2 * 1024 * 1024: raise ValueError('Notice exceeds size limit')
                    handle = nested.extractfile(member_info)
                    assert handle is not None
                    save_notice(folder, member_info.name, handle.read(2 * 1024 * 1024 + 1),
                        {'source_kind': 'checksummed_nested_archive', 'source_archive': alias, 'source_sha256': nested_sha}, row['notices'])
        if not row['notices']: raise ValueError('No recognized notice files in the pinned source')
        row['notice_state'] = 'source_notices_collected'
    except (AssertionError, ValueError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        row['notice_error'] = str(error)
    rows.append(row)
    (out / 'source-notices.json').write_text(json.dumps({'sources': rows,
        'scope': 'Recognized source notice files; not a completeness review, license interpretation, source build, or distribution clearance.'}, indent=2), encoding='utf-8')
    print(f'{source["base"]}: {row["notice_state"]} ({len(row["notices"])} files)', flush=True)
