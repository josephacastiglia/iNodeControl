"""Synthetic files only: packaging must not launch apps, read rack settings or use sockets."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import stage_release as s


class StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'repo with spaces'
        self.repo.mkdir()
        self.output = self.repo / 'output/staging/review bundle'
        self.managed = {}
        for component, name in s.MANAGED.items():
            project = self.repo / f'src/{component}/app.csproj'
            project.parent.mkdir(parents=True)
            project.write_text('<Project/>')
            (project.parent / 'Main.cs').write_text('class Main {}')
            build = self.repo / f'builds/{component}'
            build.mkdir(parents=True)
            for suffix in s.SUFFIXES:
                (build / (name+suffix)).write_bytes(b'fixture')
            runtime = {'runtimeOptions': {'framework': {'name': 'Microsoft.WindowsDesktop.App' if component == 'console' else 'Microsoft.NETCore.App', 'version':'8.0.0'}}}
            (build / (name+'.runtimeconfig.json')).write_text(json.dumps(runtime))
            (build / 'data').mkdir()
            (build / 'data/settings.json').write_text('{"do_not_package":"operator settings"}')
            record = s.bm.record(self.repo, build, project.relative_to(self.repo).as_posix())
            path = self.repo / (component+'.json')
            path.write_text(json.dumps(record))
            self.managed[component] = (build, path)
        self.native = self.repo / 'native'
        self.native.mkdir()
        (self.native / 'source.c').write_text('void fixture() {}')
        self.exe = self.repo / 'receiver.exe'
        self.exe.write_bytes(b'fixture native')
        self.native_record = self.repo / 'native.json'
        self.native_record.write_text(json.dumps({'source_sha256':{'source.c':s.bm.sha256(self.native/'source.c')},'rebuilt_sha256':s.bm.sha256(self.exe)}))
        self.guide = self.repo / 'guide.md'
        self.guide.write_text('# Review only')

    def stage(self):
        return s.stage(self.repo,self.output,self.managed,self.exe,self.native_record,self.native,self.guide)

    def test_valid_bundle_and_no_runtime_settings(self):
        with patch('subprocess.Popen', side_effect=AssertionError('must not start processes')):
            result=self.stage()
            self.assertEqual(s.verify(self.output),[])
        self.assertFalse(result['launch_allowed'])
        self.assertFalse((self.output/'payload/kernel/data').exists())
        self.assertFalse((self.output/'payload/console/data').exists())

    def test_relocated_bundle_is_independent_of_original_repo(self):
        self.stage()
        relocated=Path(self.tmp.name)/'relocated'
        shutil.copytree(self.output,relocated)
        shutil.rmtree(self.repo)
        self.assertEqual(s.verify(relocated),[])

    def test_existing_empty_directory_is_not_overwritten(self):
        self.output.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'already exists'): self.stage()
        self.assertEqual(list(self.output.iterdir()),[])

    def test_destination_cannot_be_release_or_source_or_outside_repo(self):
        for target in [self.repo/'release',self.repo/'src','C:/Windows',self.repo/'output/staging']:
            self.output=Path(target)
            with self.subTest(target=target),self.assertRaises(ValueError): self.stage()

    def test_stale_managed_source_refused_before_output_created(self):
        (self.repo/'src/console/Main.cs').write_text('changed')
        with self.assertRaisesRegex(ValueError,'no longer matches'): self.stage()
        self.assertFalse(self.output.exists())

    def test_changed_managed_build_refused(self):
        (self.managed['kernel'][0]/'iMouse2.Kernel.dll').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.stage()
        self.assertFalse(self.output.exists())

    def test_changed_native_source_refused(self):
        (self.native/'source.c').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Native source changed'): self.stage()
        self.assertFalse(self.output.exists())

    def test_changed_native_executable_refused(self):
        self.exe.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Receiver no longer matches'): self.stage()
        self.assertFalse(self.output.exists())

    def test_missing_required_build_artifact_refused_even_with_updated_record(self):
        build,record=self.managed['kernel']
        (build/'iMouse2.Kernel.runtimeconfig.json').unlink()
        record.write_text(json.dumps(s.bm.record(self.repo,build,'src/kernel/app.csproj')))
        with self.assertRaisesRegex(ValueError,'Missing runtime artifact'): self.stage()

    def test_copy_failure_never_writes_completion_manifest(self):
        with patch.object(s.shutil,'copyfile',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.stage()
        self.assertFalse((self.output/'package.json').exists())

    def test_changed_during_copy_never_writes_manifest(self):
        original=shutil.copyfile
        def corrupt(source,target):
            original(source,target)
            Path(target).write_bytes(b'changed during copy')
        with patch.object(s.shutil,'copyfile',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'while staging'): self.stage()
        self.assertFalse((self.output/'package.json').exists())

    def test_tampered_payload_fails(self):
        self.stage()
        (self.output/'payload/console/iMouse2.dll').write_bytes(b'changed')
        self.assertTrue(any('changed' in x for x in s.verify(self.output)))

    def test_missing_file_fails(self):
        self.stage()
        (self.output/'README.md').unlink()
        self.assertTrue(any('missing' in x for x in s.verify(self.output)))

    def test_extra_file_fails(self):
        self.stage()
        (self.output/'payload/console/settings.json').write_text('{}')
        self.assertTrue(any('unrecorded' in x for x in s.verify(self.output)))

    def edit_manifest(self,edit):
        p=self.output/'package.json'
        data=s.load(p);edit(data);p.write_text(json.dumps(data))

    def test_launchable_status_is_rejected(self):
        self.stage();self.edit_manifest(lambda m:m.update(launch_allowed=True))
        with self.assertRaises(ValueError):s.verify(self.output)

    def test_required_file_cannot_be_deleted_from_both_inventory_and_payload(self):
        self.stage()
        name='payload/kernel/iMouse2.Kernel.exe'
        (self.output/name).unlink();self.edit_manifest(lambda m:m['files'].pop(name))
        self.assertTrue(any('required file' in x for x in s.verify(self.output)))

    def test_rehashed_payload_must_match_embedded_build_record(self):
        self.stage();name='payload/console/iMouse2.dll'
        (self.output/name).write_bytes(b'changed')
        self.edit_manifest(lambda m:m['files'].update({name:s.row(self.output/name)}))
        self.assertTrue(any('build provenance' in x for x in s.verify(self.output)))

    def test_unapproved_asset_refused_even_if_in_inventory(self):
        self.stage();name='payload/kernel/data/devices.json'
        (self.output/name).parent.mkdir();(self.output/name).write_text('{}')
        self.edit_manifest(lambda m:m['files'].update({name:s.row(self.output/name)}))
        self.assertTrue(any('unapproved runtime' in x for x in s.verify(self.output)))

    def test_unsafe_manifest_paths_rejected(self):
        for name in ['../outside','C:/Windows/file','/absolute','dir\\file','a/./b','a//b','NUL.txt','file.','file ']:
            with self.subTest(name=name),self.assertRaises(ValueError):s.safe(self.repo,name)

    def test_duplicate_json_key_rejected(self):
        self.guide.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError,'duplicate'):s.load(self.guide)

    def test_missing_review_blocker_rejected(self):
        self.stage();self.edit_manifest(lambda m:m.update(blockers=[]))
        with self.assertRaises(ValueError):s.verify(self.output)

    def test_unexpected_framework_is_rejected(self):
        build,record=self.managed['console']
        (build/'iMouse2.runtimeconfig.json').write_text('{"runtimeOptions":{}}')
        record.write_text(json.dumps(s.bm.record(self.repo,build,'src/console/app.csproj')))
        with self.assertRaisesRegex(ValueError,'runtime requirements'):self.stage()


if __name__=='__main__':unittest.main()
