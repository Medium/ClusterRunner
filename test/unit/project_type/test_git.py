from subprocess import Popen
from unittest.mock import ANY, Mock, MagicMock

import pexpect
import re

from app.project_type.git import Git, _GitRemoteCommandExecutor
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestGit(BaseUnitTestCase):
    def setUp(self):
        super().setUp()
        self.patch('app.project_type.git.fs.create_dir')
        self.patch('os.unlink')
        self.patch('os.symlink')
        self.mock_pexpect_child = self.patch('pexpect.spawn').return_value
        self.mock_pexpect_child.before = 'None'
        self.mock_pexpect_child.exitstatus = 0

    def test_timing_file_path_happy_path(self):
        git_env = Git("ssh://scm.dev.box.net/box/www/current", 'origin',
                      'refs/changes/78/151978/27')
        timing_file = git_env.timing_file_path('QUnit')
        self.assertEquals(
            Configuration['base_directory'] +
            '/timings/master/scm.dev.box.net/box/www/current/QUnit.timing.json',
            timing_file)

    def test_execute_command_in_project_specifies_cwd_if_exists(self):
        os_path_exists_patch = self.patch('os.path.exists')
        os_path_exists_patch.return_value = True
        project_type_popen_patch = self._patch_popen()

        git_env = Git("ssh://scm.dev.box.net/box/www/current", 'origin',
                      'refs/changes/78/151978/27')
        git_env.project_directory = 'proj_dir'
        git_env.execute_command_in_project('some_command')
        project_type_popen_patch.assert_called_once_with(
            'export PROJECT_DIR="proj_dir"; some_command',
            cwd='proj_dir',
            shell=ANY,
            stdout=ANY,
            stderr=ANY,
            start_new_session=ANY, )

    def test_execute_command_in_project_type_specifies_cwd_if_doesnt_exist(self
                                                                          ):
        os_path_exists_patch = self.patch('os.path.exists')
        os_path_exists_patch.return_value = False
        project_type_popen_patch = self._patch_popen()

        git_env = Git("ssh://scm.dev.box.net/box/www/current", 'origin',
                      'refs/changes/78/151978/27')
        git_env.project_directory = 'proj_dir'
        git_env.execute_command_in_project('some_command')
        project_type_popen_patch.assert_called_once_with(
            'export PROJECT_DIR="proj_dir"; some_command',
            cwd=None,
            shell=ANY,
            stdout=ANY,
            stderr=ANY,
            start_new_session=ANY, )

    def test_execute_git_remote_command_auto_adds_known_host_if_prompted(self):
        expected_host_check_index = 3
        expected_eof_index = 0
        self.mock_pexpect_child.expect.side_effect = [
            expected_host_check_index,
            # first expect to match the host check prompt
            pexpect.TIMEOUT(None),
            # then expect no more prompts occur during the timeout
            expected_eof_index,
            # finally expect that the process finishes normally
        ]
        Configuration['git_strict_host_key_checking'] = False
        git_executor = _GitRemoteCommandExecutor()

        git_executor._execute_git_remote_command('some_command',
                                                 cwd=None,
                                                 timeout=0,
                                                 log_msg_queue=MagicMock())

        self.mock_pexpect_child.sendline.assert_called_with("yes")

    def test_execute_git_remote_command_doesnt_auto_add_known_host_if_no_prompt(
        self
    ):
        expected_eof_index = 0
        self.mock_pexpect_child.expect.side_effect = [
            pexpect.TIMEOUT(None),
            # first expect no prompts occur during the timeout
            expected_eof_index,
            # finally expect that the process finishes normally
        ]
        Configuration['git_strict_host_key_checking'] = False
        git_executor = _GitRemoteCommandExecutor()

        git_executor._execute_git_remote_command('some_command',
                                                 cwd=None,
                                                 timeout=0,
                                                 log_msg_queue=MagicMock())

        self.assertEquals(self.mock_pexpect_child.sendline.call_count, 0)

    def test_execute_git_remote_command_raises_exception_if_strict_host_checking_and_prompted(
        self
    ):
        def expect_side_effect(patterns, *args, **kwargs):
            for idx, pattern in enumerate(patterns):
                if 'Are you sure you want to continue connecting' in pattern:
                    return idx
            raise pexpect.EOF(None)

        self.mock_pexpect_child.expect.side_effect = expect_side_effect
        Configuration['git_strict_host_key_checking'] = True
        git_executor = _GitRemoteCommandExecutor()

        with self.assertRaisesRegex(RuntimeError, 'failed known_hosts check'):
            git_executor._execute_git_remote_command('some_command',
                                                     cwd=None,
                                                     timeout=0,
                                                     log_msg_queue=MagicMock())

    def test_get_full_repo_directory(self):
        Configuration['repo_directory'
                     ] = '/home/cr_user/.clusterrunner/repos/master'
        url = 'http://scm.example.com/path/to/project'

        repo_path = Git.get_full_repo_directory(url)

        self.assertEqual(
            repo_path,
            '/home/cr_user/.clusterrunner/repos/master/scm.example.com/path/to/project')

    def test_get_timing_file_directory(self):
        Configuration['timings_directory'] = '/home/cr_user/.clusterrunner/timing'
        url = 'http://scm.example.com/path/to/project'

        timings_path = Git.get_timing_file_directory(url)

        self.assertEqual(
            timings_path,
            '/home/cr_user/.clusterrunner/timing/scm.example.com/path/to/project')

    def test_get_repo_directory_removes_colon_from_directory_if_exists(self):
        Configuration['repo_directory'] = '/tmp/repos'
        git = Git("some_remote_value", 'origin', 'ref/to/some/branch')

        repo_directory = git.get_full_repo_directory(
            'ssh://source_control.cr.com:1234/master')

        self.assertEqual(repo_directory,
                         '/tmp/repos/source_control.cr.com1234/master')

    def test_get_timing_file_directory_removes_colon_from_directory_if_exists(
        self
    ):
        Configuration['timings_directory'] = '/tmp/timings'
        git = Git("some_remote_value", 'origin', 'ref/to/some/branch')

        repo_directory = git.get_timing_file_directory(
            'ssh://source_control.cr.com:1234/master')

        self.assertEqual(repo_directory,
                         '/tmp/timings/source_control.cr.com1234/master')

    def test_fetch_project_when_existing_repo_is_shallow_deletes_repo(self):
        self.patch('app.project_type.git.os.path.exists').return_value = True
        self.patch('app.project_type.git.os.path.isfile').return_value = True
        self.patch('app.project_type.git._GitRemoteCommandExecutor')
        mock_fs = self.patch('app.project_type.git.fs')
        mock_rmtree = self.patch('shutil.rmtree')

        git = Git('url')
        git._repo_directory = 'fake/repo_path'
        git._execute_and_raise_on_failure = MagicMock()
        git.execute_command_in_project = Mock(return_value=('', 0))

        mock_fs.create_dir.call_count = 0  # only measure calls made in _fetch_project
        mock_rmtree.call_count = 0

        git._fetch_project()

        mock_rmtree.assert_called_once_with('fake/repo_path')
        mock_fs.create_dir.assert_called_once_with('fake/repo_path',
                                                   Git.DIRECTORY_PERMISSIONS)

    def test_password_prompt_is_covered_by_pexpect_regexes(self):
        git_executor = _GitRemoteCommandExecutor()
        matched_prompt = False

        def expect_side_effect(patterns, *args, **kwargs):
            nonlocal matched_prompt
            if isinstance(patterns, list):
                for pattern in patterns:
                    if re.match(pattern, "Password:"):
                        matched_prompt = True
                raise pexpect.EOF(Mock())
            else:
                return 0  # pexpect returns 0 on a successful match

        self.mock_pexpect_child.expect.side_effect = expect_side_effect

        git_executor._execute_git_remote_command('fake command',
                                                 cwd=None,
                                                 timeout=0,
                                                 log_msg_queue=MagicMock())

        self.assertTrue(matched_prompt,
                        "The password prompt was not matched by pexpect")

    def test_execute_raises_broken_pipe_error_on_last_try(self):
        git_executor = _GitRemoteCommandExecutor()
        self.patch('app.project_type.git.sleep')
        self.patch('app.project_type.git.Manager').side_effect = \
            [BrokenPipeError(''), BrokenPipeError(''), BrokenPipeError('')]

        with self.assertRaises(BrokenPipeError):
            git_executor.execute('fake command',
                                 cwd=None,
                                 timeout=0,
                                 num_tries=3)

    def test_slave_param_overrides_returns_expected(self):
        self._patch_popen({
            'git rev-parse FETCH_HEAD': _FakePopenResult(stdout='deadbee123\n')
        })
        self.patch('app.project_type.git.os.path.exists').return_value = False
        self.patch('app.project_type.git.os.path.isfile').return_value = False
        self.patch('app.project_type.git._GitRemoteCommandExecutor')
        Configuration['repo_directory'] = '/repo-directory'

        git = Git(
            url='http://original-user-specified-url.test/repo-path/repo-name')
        git.fetch_project()
        actual_overrides = git.slave_param_overrides()

        expected_overrides = {
            'url':
            'ssh://fake_hostname/repodirectory/originaluserspecifiedurl.test/repopath/reponame',
            'branch': 'refs/clusterrunner/deadbee123',
        }
        self.assertEqual(expected_overrides, actual_overrides,
                         'Slave param overrides from Git object should match'
                         'expected.')

    def _patch_popen(self, command_to_result_map=None):
        """
        Mock out calls to Popen to inject fake results for specific command strings.

        :param command_to_result_map: A dict that maps a command string regex to a _FakePopenResult object
        :type command_to_result_map: dict[str, _FakePopenResult]
        :return: The patched popen constructor mock
        :rtype: MagicMock
        """
        command_to_result_map = command_to_result_map or {}
        self.patch('app.project_type.project_type.TemporaryFile',
                   new=lambda: Mock())
        project_type_popen_patch = self.patch(
            'app.project_type.project_type.Popen')

        def fake_popen_constructor(command, stdout, stderr, *args, **kwargs):
            fake_result = _FakePopenResult()  # default value
            for command_regex in command_to_result_map:
                if re.search(command_regex, command):
                    fake_result = command_to_result_map[command_regex]
                    break
            stdout.read.return_value = fake_result.stdout.encode()
            stderr.read.return_value = fake_result.stderr.encode()
            return Mock(spec=Popen, returncode=fake_result.return_code)

        project_type_popen_patch.side_effect = fake_popen_constructor
        return project_type_popen_patch


class _FakePopenResult:
    def __init__(self, return_code=0, stdout='', stderr=''):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
