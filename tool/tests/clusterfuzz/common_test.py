"""Test the 'common' module."""
# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import cStringIO
import subprocess
import os
import stat
import mock

from clusterfuzz import common
import helpers


class GetVersionTest(helpers.ExtendedTestCase):
  """Tests get_version."""

  def setUp(self):
    self.setup_fake_filesystem()

  def test_get_version(self):
    """Test get_version."""
    version_path = os.path.join(
        os.path.dirname(common.__file__), 'resources', 'VERSION')
    self.fs.CreateFile(version_path, contents='vvv')
    self.assertEqual('vvv', common.get_version())


class ConfirmTest(helpers.ExtendedTestCase):
  """Tests the confirm method."""

  def setUp(self):
    helpers.patch(self, ['__builtin__.raw_input'])

  def test_yes_default(self):
    """Tests functionality with yes as default."""

    self.mock.raw_input.side_effect = ['y', 'n', '']

    self.assertTrue(common.confirm('A question'))
    self.assertFalse(common.confirm('A question'))
    self.assertTrue(common.confirm('A question'))

    self.mock.raw_input.assert_has_calls([mock.call('A question [Y/n]: ')])
    self.assert_n_calls(3, [self.mock.raw_input])

  def test_no_default(self):
    """Tests functionality when no is the default."""

    self.mock.raw_input.side_effect = ['y', 'n', '']

    self.assertTrue(common.confirm('A question', default='n'))
    self.assertFalse(common.confirm('A question', default='n'))
    self.assertFalse(common.confirm('A question', default='n'))

    self.mock.raw_input.assert_has_calls([mock.call('A question [y/N]: ')])
    self.assert_n_calls(3, [self.mock.raw_input])

  def test_empty_default(self):
    """Tests functionality when default is explicitly None."""

    self.mock.raw_input.side_effect = ['y', 'n', '', 'n']

    self.assertTrue(common.confirm('A question', default=None))
    self.assertFalse(common.confirm('A question', default=None))
    self.assertFalse(common.confirm('A question', default=None))

    self.mock.raw_input.assert_has_calls([
        mock.call('A question [y/n]: '),
        mock.call('Please type either "y" or "n": ')])
    self.assert_n_calls(4, [self.mock.raw_input])

  def test_quiet_mode(self):
    """Tests functinality in quiet mode."""
    self.mock_os_environment({'CF_QUIET': '1'})

    self.assertTrue(common.confirm('Anything'))
    self.assertTrue(common.confirm('Anything', default='n'))

    self.assert_n_calls(0, [self.mock.raw_input])

class ExecuteTest(helpers.ExtendedTestCase):
  """Tests the execute method."""

  def setUp(self):
    helpers.patch(self, ['subprocess.Popen',
                         'logging.getLogger',
                         'logging.config.dictConfig',
                         'clusterfuzz.common.check_binary',
                         'clusterfuzz.common.wait_timeout',
                         'clusterfuzz.common.interpret_ninja_output',
                         'os.environ.copy'])
    self.mock.copy.return_value = {'OS': 'ENVIRON'}
    self.mock.dictConfig.return_value = {}

    from clusterfuzz import local_logging
    local_logging.start_loggers()
    self.lines = 'Line 1\nLine 2\nLine 3'

  def build_popen_mock(self, code):
    """Builds the mocked Popen object."""
    return mock.MagicMock(
        stdout=cStringIO.StringIO(self.lines),
        returncode=code)

  def test_with_ninja(self):
    """Ensure interpret_ninja_output is run when the ninja flag is set."""

    x = mock.Mock()
    x.read.side_effect = ['part1', 'part2\n']
    self.mock.Popen.return_value = mock.Mock(stdout=x, returncode=0)
    common.execute('ninja', 'do this plz', '~/working/directory',
                   print_output=True, exit_on_error=True,
                   env={'a': 'b', 1: 2, 'c': None})
    self.assert_n_calls(1, [self.mock.interpret_ninja_output])
    self.mock.Popen.assert_called_once_with(
        'ninja do this plz',
        shell=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd='~/working/directory',
        env={'a': 'b', 'OS': 'ENVIRON', '1': '2'},
        preexec_fn=os.setsid
    )

  def run_execute(self, print_cmd, print_out, exit_on_err):
    return common.execute(
        'cmd', '',
        '~/working/directory',
        print_command=print_cmd,
        print_output=print_out,
        exit_on_error=exit_on_err)

  def run_popen_assertions(
      self, code, print_cmd=True, print_out=True, exit_on_err=True):
    """Runs the popen command and tests the output."""

    self.mock.Popen.reset_mock()
    self.mock.Popen.return_value = self.build_popen_mock(code)
    self.mock.Popen.return_value.wait.return_value = True
    return_code = returned_lines = None
    will_exit = exit_on_err and code != 0

    if will_exit:
      with self.assertRaises(SystemExit):
        return_code, returned_lines = self.run_execute(
            print_cmd, print_out, exit_on_err)
    else:
      return_code, returned_lines = self.run_execute(
          print_cmd, print_out, exit_on_err)

    self.assertEqual(return_code, None if will_exit else code)
    self.assertEqual(returned_lines, None if will_exit else self.lines)
    self.assert_exact_calls(self.mock.Popen.return_value.wait, [mock.call()])
    self.assert_exact_calls(self.mock.Popen, [
        mock.call(
            'cmd',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            cwd='~/working/directory',
            env={'OS': 'ENVIRON'},
            preexec_fn=os.setsid),
    ])

  def test_process_runs_successfully(self):
    """Test execute when the process successfully runs."""

    return_code = 0
    for print_cmd in [True, False]:
      for print_out in [True, False]:
        for exit_on_error in [True, False]:
          self.run_popen_assertions(
              return_code, print_cmd, print_out, exit_on_error)

  def test_process_run_fails(self):
    """Test execute when the process does not run successfully."""

    return_code = 1
    for print_cmd in [True, False]:
      for print_out in [True, False]:
        for exit_on_error in [True, False]:
          self.run_popen_assertions(
              return_code, print_cmd, print_out, exit_on_error)

  def test_check_binary_fail(self):
    """Test check_binary fail."""
    self.mock.check_binary.side_effect = common.NotInstalledError('cmd')

    with self.assertRaises(common.NotInstalledError) as cm:
      common.execute('cmd', 'aaa', '~/working/directory')

    self.assert_exact_calls(
        self.mock.check_binary, [mock.call('cmd', '~/working/directory')])
    self.assertEqual(
        'cmd is not found. Please install it or ensure the path is correct.',
        cm.exception.message)


class CheckBinaryTest(helpers.ExtendedTestCase):
  """Test check_binary."""

  def setUp(self):
    helpers.patch(self, ['subprocess.check_output'])

  def test_valid(self):
    """Test a valid binary."""
    common.check_binary('test', 'cwd')
    self.mock.check_output.assert_called_once_with(['which', 'test'], cwd='cwd')

  def test_invalid(self):
    """Test an invalid binary."""
    self.mock.check_output.side_effect = subprocess.CalledProcessError(1, '')
    with self.assertRaises(common.NotInstalledError) as cm:
      common.check_binary('test', 'cwd')

    self.mock.check_output.assert_called_once_with(['which', 'test'], cwd='cwd')
    self.assertEqual(
        'test is not found. Please install it or ensure the path is correct.',
        cm.exception.message)


class StoreAuthHeaderTest(helpers.ExtendedTestCase):
  """Tests the store_auth_header method."""

  def setUp(self):
    self.setup_fake_filesystem()
    self.auth_header = 'Bearer 12345'

  def test_folder_absent(self):
    """Tests storing when the folder has not been created prior."""

    self.assertFalse(os.path.exists(common.CLUSTERFUZZ_CACHE_DIR))
    common.store_auth_header(self.auth_header)

    self.assertTrue(os.path.exists(common.CLUSTERFUZZ_CACHE_DIR))
    with open(common.AUTH_HEADER_FILE, 'r') as f:
      self.assertEqual(f.read(), self.auth_header)
    self.assert_file_permissions(common.AUTH_HEADER_FILE, 600)

  def test_folder_present(self):
    """Tests storing when the folder has already been created."""

    self.fs.CreateFile(common.AUTH_HEADER_FILE)
    common.store_auth_header(self.auth_header)

    with open(common.AUTH_HEADER_FILE, 'r') as f:
      self.assertEqual(f.read(), self.auth_header)
    self.assert_file_permissions(common.AUTH_HEADER_FILE, 600)


class GetStoredAuthHeaderTest(helpers.ExtendedTestCase):
  """Tests the stored_auth_key method."""

  def setUp(self):
    self.setup_fake_filesystem()

  def test_file_missing(self):
    """Tests functionality when auth key file does not exist."""

    result = common.get_stored_auth_header()
    self.assertEqual(result, None)

  def test_permissions_incorrect(self):
    """Tests functionality when file exists but permissions wrong."""

    self.fs.CreateFile(common.AUTH_HEADER_FILE)
    os.chmod(common.AUTH_HEADER_FILE, stat.S_IWGRP)

    with self.assertRaises(common.PermissionsTooPermissiveError) as ex:
      result = common.get_stored_auth_header()
      self.assertEqual(result, None)
    self.assertIn(
        'File permissions too permissive to open',
        ex.exception.message)

  def test_file_valid(self):
    """Tests when file is accessible and auth key is returned."""

    self.fs.CreateFile(common.AUTH_HEADER_FILE, contents='Bearer 1234')
    os.chmod(common.AUTH_HEADER_FILE, stat.S_IWUSR|stat.S_IRUSR)

    result = common.get_stored_auth_header()
    self.assertEqual(result, 'Bearer 1234')


class CheckConfirmTest(helpers.ExtendedTestCase):
  """Tests the check_confirm method."""

  def setUp(self):
    helpers.patch(self, ['clusterfuzz.common.confirm'])

  def test_answer_yes(self):
    self.mock.confirm.return_value = True
    common.check_confirm('Question?')
    self.assert_exact_calls(self.mock.confirm, [mock.call('Question?')])

  def test_answer_no(self):
    self.mock.confirm.return_value = False
    with self.assertRaises(SystemExit):
      common.check_confirm('Question?')
    self.assert_exact_calls(self.mock.confirm, [mock.call('Question?')])


class AskTest(helpers.ExtendedTestCase):
  """Tests the ask method."""

  def setUp(self):
    helpers.patch(self, ['__builtin__.raw_input'])
    self.mock.raw_input.side_effect = [
        'wrong', 'still wrong', 'very wrong', 'correct']

  def test_returns_when_correct(self):
    """Tests that the method only returns when the answer fits validation."""

    question = 'Initial Question'
    error_message = 'Please answer correctly'
    validate_fn = lambda x: x == 'correct'

    result = common.ask(question, error_message, validate_fn)
    self.assert_n_calls(4, [self.mock.raw_input])
    self.mock.raw_input.assert_has_calls([
        mock.call('Initial Question: '),
        mock.call('Please answer correctly: ')])
    self.assertEqual(result, 'correct')


class GetBinaryNameTest(helpers.ExtendedTestCase):
  """Test get_binary_name."""

  def test_running_command(self):
    """Test 'Running Command: '."""
    binary_name = common.get_binary_name([
        {'content': 'aaa'},
        {'content': 'Running command: aaa/bbb/some_fuzzer something'},
        {'content': 'bbb'}
    ])
    self.assertEqual('some_fuzzer', binary_name)

  def test_no_command(self):
    """Raise an exception when there's no command."""
    with self.assertRaises(Exception):
      common.get_binary_name([
          {'content': 'aaa'}
      ])


class BinaryDefinitionTest(helpers.ExtendedTestCase):
  """Tests the BinaryDefinition class."""

  def test_no_sanitizer(self):
    with self.assertRaises(common.SanitizerNotProvidedError):
      common.BinaryDefinition('builder', 'CHROME_SRC', 'reproducer')


class WaitTimeoutTest(helpers.ExtendedTestCase):
  """Tests the wait_timeout method."""

  def setUp(self):
    helpers.patch(self, ['time.sleep',
                         'os.getpgid',
                         'os.killpg'])

  def test_kill_not_needed(self):
    """Tests when the process exits without needing to be killed."""

    class ProcMock(object):
      poll_results = [1, None, None, None]
      pid = 1234
      def poll(self):
        return self.poll_results.pop()
    proc = ProcMock()

    common.wait_timeout(proc, 5)

    self.assert_n_calls(0, [self.mock.killpg])
    self.assert_exact_calls(self.mock.sleep, [mock.call(0.5), mock.call(0.5),
                                              mock.call(0.5), mock.call(0.5)])

  def test_kill_needed(self):
    """Tests when the process must be killed."""

    self.mock.getpgid.return_value = 345
    class ProcMock(object):
      pid = 1234
      def poll(self):
        return None
    proc = ProcMock()

    common.wait_timeout(proc, 5)

    self.assert_exact_calls(self.mock.killpg, [mock.call(345, 15)])
    self.assert_exact_calls(self.mock.getpgid, [mock.call(1234)])
    self.assert_n_calls(11, [self.mock.sleep])

  def test_no_timeout(self):
    """Tests when no timeout is specified."""

    common.wait_timeout(mock.Mock(), None)

    self.assert_n_calls(0, [self.mock.sleep, self.mock.getpgid,
                            self.mock.killpg])

  def test_no_process(self):
    """Tests when process died maturely."""
    error = OSError()
    error.errno = 3  # No such process.
    self.mock.killpg.side_effect = error

    self.mock.getpgid.return_value = 345
    class ProcMock(object):
      pid = 1234
      def poll(self):
        return None
    proc = ProcMock()

    common.wait_timeout(proc, 5)

    self.assert_exact_calls(self.mock.killpg, [mock.call(345, 15)])
    self.assert_exact_calls(self.mock.getpgid, [mock.call(1234)])
    self.assert_n_calls(10, [self.mock.sleep])

  def test_kill_error(self):
    """Test error when killing."""
    error = OSError()
    error.errno = 4
    self.mock.killpg.side_effect = error

    self.mock.getpgid.return_value = 345
    class ProcMock(object):
      pid = 1234
      def poll(self):
        return None
    proc = ProcMock()

    with self.assertRaises(OSError):
      common.wait_timeout(proc, 5)

    self.assert_exact_calls(self.mock.killpg, [mock.call(345, 15)])
    self.assert_exact_calls(self.mock.getpgid, [mock.call(1234)])
    self.assert_n_calls(10, [self.mock.sleep])


class InterpretNinjaOutputTest(helpers.ExtendedTestCase):
  """Tests the interpret_ninja_output method."""

  def setUp(self):
    helpers.patch(self, ['clusterfuzz.common.print_progress_bar'])

  def test_invalid_string(self):
    """Ensures it doesn't try to print from an invalid input."""

    common.interpret_ninja_output('wrong')
    self.assert_n_calls(0, [self.mock.print_progress_bar])

  def test_correct_parsing(self):
    """Ensure valid ninja commands are parsed correctly."""

    common.interpret_ninja_output('[23/100] CXX ../file/name /second/file')
    self.assert_exact_calls(self.mock.print_progress_bar, [
        mock.call(23, 100, prefix='Ninja progress:')])


class PrintProgressBarTest(helpers.ExtendedTestCase):
  """Ensures the print_progress_bar method works properly."""

  def setUp(self):
    helpers.patch(self,
                  ['__builtin__.print',
                   'backports.shutil_get_terminal_size.get_terminal_size'])
    self.mock.get_terminal_size.return_value = mock.Mock(columns=150)
    reload(common)

  def test_call(self):
    """Ensures print is called with the correct parameters."""

    result = common.print_progress_bar(50, 100, prefix='Progress')
    bar = '|%s%s|' % ('=' * 50, '-' * 50)
    self.assertEqual(result, '\rProgress %s 50.0%% ' % bar)
    result = common.print_progress_bar(100, 100, prefix='Progress')
    bar = '|%s|' % ('=' * 100)
    self.assertEqual(result, '\rProgress %s 100.0%% ' % bar)


class DeleteIfExistsTest(helpers.ExtendedTestCase):
  """Tests the delete_if_exists method."""

  def setUp(self):
    self.setup_fake_filesystem()

  def test_deletes_file(self):
    """Ensure the file gets deleted."""

    home = os.path.expanduser('~')
    directory = os.path.join(home, 'testcase')
    filename = os.path.join(directory, 'testcase.js')
    os.makedirs(directory)
    with open(filename, 'w') as f:
      f.write('text')
    self.assertTrue(os.path.isfile(filename))

    common.delete_if_exists(directory)

    self.assertFalse(os.path.exists(directory))


class GetSourceDirectoryTest(helpers.ExtendedTestCase):
  """Tests the get_source_directory method."""

  def setUp(self):
    self.setup_fake_filesystem()
    helpers.patch(self, ['clusterfuzz.common.ask'])
    self.source_dir = '~/chromium/src'

  def test_get_from_environment(self):
    """Tests getting the source directory from the os environment."""

    self.mock_os_environment({'CHROMIUM_SRC': self.source_dir})
    result = common.get_source_directory('chromium')

    self.assertEqual(result, self.source_dir)
    self.assertEqual(0, self.mock.ask.call_count)

  def test_ask_and_expand_user(self):
    """Tests getting the source directory and expand user."""

    self.mock_os_environment({'CHROMIUM_SRC': ''})
    os.makedirs(os.path.expanduser('~/test-dir'))
    self.mock.ask.return_value = '~/test-dir'

    result = common.get_source_directory('chromium')
    self.assertEqual(os.path.expanduser('~/test-dir'), result)

  def test_ask_and_expand_path(self):
    """Tests getting the source directory and expand abspath."""

    self.mock_os_environment({'CHROMIUM_SRC': ''})
    os.makedirs(os.path.abspath('./test-dir'))
    self.mock.ask.return_value = './test-dir'

    result = common.get_source_directory('chromium')
    self.assertEqual(os.path.abspath('./test-dir'), result)


class GetValidAbsDirTest(helpers.ExtendedTestCase):
  """Tests for get_valid_abs_dir."""

  def setUp(self):
    self.setup_fake_filesystem()

  def test_validity(self):
    """Test a valid dir."""
    os.makedirs('/test/test2')
    self.assertEqual('/test/test2', common.get_valid_abs_dir('/test/test2'))
    self.assertIsNone(common.get_valid_abs_dir('/test/test3'))

  def test_empty(self):
    """Test empty."""
    self.assertIsNone(common.get_valid_abs_dir(''))


class ExecuteWithShellTest(helpers.ExtendedTestCase):
  """Tests for execute_with_shell."""

  def setUp(self):
    helpers.patch(self, [
        'os.system', 'clusterfuzz.common.check_binary'
    ])

  def test_execute(self):
    """Test execute."""
    common.execute_with_shell('test', 'args', '/dir')

    self.mock.check_binary.assert_called_once_with('test', '/dir')
    self.mock.system.assert_called_once_with('cd /dir && test args')


class GetStdinAndFilterArgsTest(helpers.ExtendedTestCase):
  """Tests for get_stdin_and_filter_args."""

  def setUp(self):
    self.setup_fake_filesystem()
    with open('/testcase', 'wb') as file_handle:
      file_handle.write('PASS')

  def test_without_piped_input(self):
    """Test without piped input."""
    stdin_handle, args = common.get_stdin_and_filter_args(
        '--arg1 /testcase')
    self.assertEqual(args, '--arg1 /testcase')
    self.assertEqual(stdin_handle, subprocess.PIPE)

  def test_with_piped_input(self):
    """Test with piped input."""
    stdin_handle, args = common.get_stdin_and_filter_args(
        '--arg1 < /testcase')
    self.assertEqual(args, '--arg1')
    self.assertEqual(stdin_handle.read(), 'PASS')
