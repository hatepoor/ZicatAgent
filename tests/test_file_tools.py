"""文件工具专项测试：grep / glob / file_apply_patch 与读写加固。"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from agent_types import exhaust
from tools.context import ToolContext
from tools.files import do_file_patch, do_file_read, do_file_write
from tools.files.apply_patch import do_file_apply_patch
from tools.files.search import do_grep, do_glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeHandler:
    def __init__(self, cwd):
        self.cwd = cwd
        self.parent = self
        self.working = {}
        self.history_info = []
        self.code_stop_signal = []
        self.current_turn = 0
        self.print = lambda *a, **k: None

    def get_ctx_multiplier(self):
        return 1.0

    def _get_anchor_prompt(self, skip=False):
        return ''


def call(fn, ctx, args, content=''):
    outcome = exhaust(fn(ctx, args, SimpleNamespace(content=content)))
    return outcome.data if hasattr(outcome, 'data') else outcome


class FileToolBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='zicat_filetest_', dir=os.path.join(ROOT, 'temp'))
        self.ctx = ToolContext(FakeHandler(self.dir))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, rel, text, encoding='utf-8', newline=''):
        path = os.path.join(self.dir, rel)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, 'w', encoding=encoding, newline=newline) as f:
            f.write(text)
        return path


class GrepTests(FileToolBase):
    def setUp(self):
        super().setUp()
        self.write('a.py', 'alpha\nbeta\n')
        self.write('sub/b.py', 'beta\ngamma\n')
        self.write('c.txt', 'beta\n')
        self.write('.git/d.py', 'beta\n')

    def tearDown(self):
        os.environ.pop('ZICAT_NO_RG', None)
        super().tearDown()

    def test_grep_matches_and_files_only(self):
        result = call(do_grep, self.ctx,
                      {'pattern': 'beta', 'path': '.', 'max_results': 10})
        self.assertIn('a.py', result)
        self.assertIn('sub/b.py', result)
        self.assertIsInstance(result, str)
        self.assertIn('[3 matches in 3 files]', result)

        files = call(do_grep, self.ctx,
                     {'pattern': 'beta', 'path': '.', 'files_only': True})
        self.assertIn('a.py', files)
        self.assertIn('[3 files]', files)

    def test_grep_glob_filter(self):
        result = call(do_grep, self.ctx,
                      {'pattern': 'beta', 'path': '.', 'glob': '*.py'})
        self.assertIn('a.py', result)
        self.assertIn('sub/b.py', result)
        self.assertNotIn('c.txt', result)

    def test_grep_fallback_matches_rg(self):
        normal = call(do_grep, self.ctx, {'pattern': 'beta', 'path': '.', 'max_results': 10})
        os.environ['ZICAT_NO_RG'] = '1'
        fallback = call(do_grep, self.ctx, {'pattern': 'beta', 'path': '.', 'max_results': 10})
        os.environ.pop('ZICAT_NO_RG', None)
        self.assertIn('[fallback: ripgrep unavailable]', fallback)
        for path in ('a.py', 'sub/b.py', 'c.txt'):
            self.assertIn(path, normal)
            self.assertIn(path, fallback)

    def test_grep_invalid_regex(self):
        result = call(do_grep, self.ctx, {'pattern': '[', 'path': '.'})
        self.assertIn('Error', result)

    def test_grep_missing_path(self):
        result = call(do_grep, self.ctx, {'pattern': 'x', 'path': 'nope'})
        self.assertIn('path not found', result)

    def test_grep_max_results(self):
        result = call(do_grep, self.ctx,
                      {'pattern': 'beta', 'path': '.', 'max_results': 2})
        self.assertIn('truncated at 2', result)

    def test_glob(self):
        result = call(do_glob, self.ctx, {'pattern': '*.py', 'path': '.'})
        self.assertIn('a.py', result)
        self.assertIn('sub/b.py', result)
        self.assertNotIn('c.txt', result)

    def test_glob_fallback(self):
        os.environ['ZICAT_NO_RG'] = '1'
        result = call(do_glob, self.ctx, {'pattern': '*.py', 'path': '.'})
        self.assertIn('a.py', result)
        self.assertIn('[fallback: ripgrep unavailable]', result)


class ApplyPatchTests(FileToolBase):
    def patch(self, text):
        return call(do_file_apply_patch, self.ctx, {'patch': text})

    def test_multi_file_add_update_delete(self):
        self.write('a.py', 'alpha\nbeta\n')
        self.write('b.py', 'one\ntwo\n')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "@@\n"
            "-beta\n"
            "+BETA\n"
            "*** Add File: sub/new.py\n"
            "+created\n"
            "*** Delete File: b.py\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'success')
        with open(os.path.join(self.dir, 'a.py'), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'alpha\nBETA\n')
        with open(os.path.join(self.dir, 'sub', 'new.py'), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'created\n')
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'b.py')))

    def test_multi_hunk(self):
        self.write('a.py', 'one\ntwo\nthree\nfour\n')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "@@\n"
            "-one\n"
            "+ONE\n"
            "@@\n"
            "-four\n"
            "+FOUR\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'success')
        with open(os.path.join(self.dir, 'a.py'), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'ONE\ntwo\nthree\nFOUR\n')

    def test_move(self):
        self.write('a.py', 'alpha\n')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "*** Move to: sub/moved.py\n"
            "@@\n"
            "-alpha\n"
            "+ALPHA\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'success')
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'a.py')))
        with open(os.path.join(self.dir, 'sub', 'moved.py'), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'ALPHA\n')

    def test_whitespace_tolerance(self):
        self.write('a.py', 'line one   \nline two\n')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "@@\n"
            "-line one\n"
            "+line 1\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'success')
        with open(os.path.join(self.dir, 'a.py'), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'line 1\nline two\n')

    def test_ambiguous_hunk_does_not_write(self):
        path = self.write('a.py', 'same\nsame\n')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "@@\n"
            "-same\n"
            "+changed\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'error')
        with open(path, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'same\nsame\n')

    def test_missing_context_does_not_write(self):
        path = self.write('a.py', 'alpha\n')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "@@\n"
            "-nope\n"
            "+changed\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'error')
        with open(path, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'alpha\n')

    def test_insert_after_context(self):
        self.write('a.py', 'alpha\nbeta\n')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "@@ alpha\n"
            "+inserted\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'success')
        with open(os.path.join(self.dir, 'a.py'), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'alpha\ninserted\nbeta\n')

    def test_crlf_preserved(self):
        path = self.write('a.py', 'alpha\r\nbeta\r\n')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "@@\n"
            "-alpha\n"
            "+ALPHA\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'success')
        with open(path, 'rb') as f:
            data = f.read()
        self.assertIn(b'ALPHA\r\n', data)
        self.assertEqual(data.count(b'\r\n'), 2)
        self.assertEqual(data.replace(b'\r\n', b'').count(b'\n'), 0)

    def test_gbk_preserved(self):
        original = '中文内容\n第二行\n'
        path = self.write('a.txt', original, encoding='gbk')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Update File: a.txt\n"
            "@@\n"
            "-第二行\n"
            "+第三行\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'success')
        with open(path, 'rb') as f:
            raw = f.read()
        self.assertEqual(raw.decode('gbk'), '中文内容\n第三行\n')

    def test_utf8_bom_preserved(self):
        path = os.path.join(self.dir, 'a.txt')
        with open(path, 'wb') as f:
            f.write(b'\xef\xbb\xbfalpha\n')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Update File: a.txt\n"
            "@@\n"
            "-alpha\n"
            "+ALPHA\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'success')
        with open(path, 'rb') as f:
            self.assertTrue(f.read().startswith(b'\xef\xbb\xbf'))

    def test_add_existing_fails(self):
        self.write('a.py', 'alpha\n')
        result = self.patch(
            "*** Begin Patch\n"
            "*** Add File: a.py\n"
            "+new\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'error')

    def test_rollback_on_write_failure(self):
        a = self.write('a.py', 'alpha\n')
        b = self.write('b.py', 'beta\n')
        from tools.files import apply_patch as apply_module

        real = apply_module.atomic_write
        calls = {'n': 0}

        def flaky(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 2:
                raise OSError('disk full')
            return real(*args, **kwargs)

        result = None
        with mock.patch.object(apply_module, 'atomic_write', side_effect=flaky):
            result = self.patch(
                "*** Begin Patch\n"
                "*** Update File: a.py\n"
                "@@\n"
                "-alpha\n"
                "+ALPHA\n"
                "*** Update File: b.py\n"
                "@@\n"
                "-beta\n"
                "+BETA\n"
                "*** End Patch\n")
        self.assertEqual(result['status'], 'error')
        with open(a, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'alpha\n')
        with open(b, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'beta\n')

    def test_path_outside_allowed_roots_blocked(self):
        result = self.patch(
            "*** Begin Patch\n"
            "*** Add File: C:/Windows/System32/zicat_should_not_exist.txt\n"
            "+x\n"
            "*** End Patch\n")
        self.assertEqual(result['status'], 'error')
        self.assertIn('允许目录', result['msg'])


class FileReadWriteTests(FileToolBase):
    def test_read_gbk(self):
        path = self.write('a.txt', '中文内容\n', encoding='gbk')
        result = call(do_file_read, self.ctx, {'path': 'a.txt', 'show_linenos': False})
        self.assertIn('中文内容', result)

    def test_patch_gbk_preserved(self):
        path = self.write('a.txt', '中文内容\n第二行\n', encoding='gbk')
        result = call(do_file_patch, self.ctx, {
            'path': 'a.txt', 'old_content': '第二行', 'new_content': '第三行'})
        self.assertEqual(result['status'], 'success')
        with open(path, 'rb') as f:
            self.assertEqual(f.read().decode('gbk'), '中文内容\n第三行\n')

    def test_write_gbk_preserved(self):
        path = self.write('a.txt', '旧内容\n', encoding='gbk')
        result = call(do_file_write, self.ctx, {
            'path': 'a.txt', 'content': '新内容\n', 'mode': 'overwrite'})
        self.assertEqual(result['status'], 'success')
        with open(path, 'rb') as f:
            self.assertEqual(f.read().decode('gbk'), '新内容\n')

    def test_append_bom_not_duplicated(self):
        path = os.path.join(self.dir, 'a.txt')
        with open(path, 'wb') as f:
            f.write(b'\xef\xbb\xbfalpha\n')
        result = call(do_file_write, self.ctx, {
            'path': 'a.txt', 'content': 'beta\n', 'mode': 'append'})
        self.assertEqual(result['status'], 'success')
        with open(path, 'rb') as f:
            data = f.read()
        self.assertEqual(data.count(b'\xef\xbb\xbf'), 1)
        self.assertTrue(data.endswith(b'beta\n'))

    def test_write_sensitive_blocked(self):
        result = call(do_file_write, self.ctx, {'path': '.env', 'content': 'SECRET=1'})
        self.assertEqual(result['status'], 'error')
        self.assertFalse(os.path.exists(os.path.join(self.dir, '.env')))

    def test_write_outside_root_blocked(self):
        result = call(do_file_write, self.ctx, {
            'path': 'C:/Windows/System32/zicat_should_not_exist.txt', 'content': 'x'})
        self.assertEqual(result['status'], 'error')


if __name__ == '__main__':
    unittest.main()
