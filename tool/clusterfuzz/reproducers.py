"""Classes to reproduce different types of testcases."""
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

import os
import re
import shutil
import time
import subprocess
import logging
import json
import HTMLParser
import sys
import requests
import xvfbwrapper
import psutil

from clusterfuzz import common

DEFAULT_GESTURE_TIME = 5
logger = logging.getLogger('clusterfuzz')


def strip_html(lines):
  """Strip HTML tags and escape HTML chars."""
  new_lines = []
  parser = HTMLParser.HTMLParser()

  for line in lines:
    # We only strip <a> because that's all we need.
    line = re.sub('<[/a][^<]+?>', '', line)
    new_lines.append(parser.unescape(line))

  return new_lines


def get_only_first_stacktrace(lines):
  """Get the first stacktrace because multiple stacktraces would make stacktrace
    parsing wrong."""
  new_lines = []
  for line in lines:
    line = line.rstrip()
    if line.startswith('+----') and new_lines:
      break
    # We don't add the empty lines in the beginning.
    if new_lines or line:
      new_lines.append(line)
  return new_lines


def maybe_fix_dict_args(args, build_dir):
  """Fix the dict args of libfuzzer args if exists."""
  dict_path = args.get('dict')
  if dict_path:
    args['dict'] = os.path.join(build_dir, os.path.basename(dict_path))
  return args


def deserialize_libfuzzer_args(args_str):
  """Deserialize libfuzzer's args, e.g. -dict=something."""
  args = {}
  for kvs in args_str.split(' '):
    kvs = kvs.strip()
    if not kvs:
      continue
    tokens = kvs.split('=')
    args[tokens[0].lstrip('-')] = tokens[1]
  return args


def serialize_libfuzzer_args(args):
  """Serialize a dict to libfuzzer's args, e.g. -dict=something."""
  args_list = []
  for key, value in args.iteritems():
    args_list.append('-%s=%s' % (key, value))

  return ' '.join(sorted(args_list))


def is_similar(new_type, new_state_lines, original_type, original_state_lines):
  """Check if the new state is similar enough to the original state."""
  count = 0
  if new_type == original_type:
    count += 1

  for line in new_state_lines:
    if line in original_state_lines:
      count += 1

  return count >= len(original_state_lines)


class BaseReproducer(object):
  """The basic reproducer class that all other ones are built on."""

  def get_gesture_start_time(self):
    """Determine how long to sleep before running gestures."""

    if self.gestures[-1].startswith('Trigger'):
      gesture_start_time = int(self.gestures[-1].split(':')[1])
      self.gestures.pop()
    else:
      gesture_start_time = DEFAULT_GESTURE_TIME
    return gesture_start_time

  def __init__(self, binary_provider, testcase, sanitizer, disable_blackbox,
               target_args):
    self.testcase_path = testcase.get_testcase_path()
    self.job_type = testcase.job_type
    self.environment = testcase.environment
    self.args = testcase.reproduction_args + ' ' + target_args
    self.binary_path = binary_provider.get_binary_path()
    self.symbolizer_path = common.get_resource(
        0755, 'resources', 'llvm-symbolizer')
    self.sanitizer = sanitizer
    self.gestures = testcase.gestures
    self.disable_blackbox = disable_blackbox

    stacktrace_lines = strip_html(
        [l['content'] for l in testcase.stacktrace_lines])
    stacktrace_lines = get_only_first_stacktrace(stacktrace_lines)
    self.crash_state, self.crash_type = self.get_stacktrace_info(
        '\n'.join(stacktrace_lines))

    self.gesture_start_time = (self.get_gesture_start_time() if self.gestures
                               else None)
    self.source_directory = binary_provider.source_directory

  def deserialize_sanitizer_options(self, options):
    """Read options from a variable like ASAN_OPTIONS into a dict."""

    pairs = options.split(':')
    return_dict = {}
    for pair in pairs:
      k, v = pair.split('=')
      return_dict[k] = v
    return return_dict


  def serialize_sanitizer_options(self, options):
    """Takes dict of sanitizer options, returns command-line friendly string."""

    pairs = []
    for key, value in options.iteritems():
      pairs.append('%s=%s' % (key, value))
    return ':'.join(pairs)

  def set_up_symbolizers_suppressions(self):
    """Sets up the symbolizer variables for an environment."""

    env = self.environment
    env['%s_SYMBOLIZER_PATH' % self.sanitizer] = self.symbolizer_path
    env['DISPLAY'] = ':0.0'
    for variable in env:
      if '_OPTIONS' not in variable:
        continue
      options = self.deserialize_sanitizer_options(env[variable])

      if 'external_symbolizer_path' in options:
        options['external_symbolizer_path'] = self.symbolizer_path
      if 'suppressions' in options:
        suppressions_map = {'UBSAN_OPTIONS': 'ubsan', 'LSAN_OPTIONS': 'lsan'}
        filename = common.get_resource(
            0640, 'resources', 'suppressions',
            '%s_suppressions.txt' % suppressions_map[variable])
        options['suppressions'] = filename
      env[variable] = self.serialize_sanitizer_options(options)
    self.environment = env

  def pre_build_steps(self):
    """Steps to run before building."""
    self.set_up_symbolizers_suppressions()

  def reproduce_crash(self):
    """Reproduce the crash."""

    self.pre_build_steps()

    command = '%s %s %s' % (self.binary_path, self.args, self.testcase_path)
    return common.execute(command, os.path.dirname(self.binary_path),
                          environment=self.environment, exit_on_error=False)

  def get_stacktrace_info(self, trace):
    """Post a stacktrace, return (crash_state, crash_type)."""

    response = requests.post(
        url=('https://clusterfuzz.com/v2/parse_stacktrace'),
        data=json.dumps({'job': self.job_type, 'stacktrace': trace}))
    response = json.loads(response.text)
    crash_state = [x for x in response['crash_state'].split('\n') if x]
    crash_type = response['crash_type'].replace('\n', ' ')
    return crash_state, crash_type

  def reproduce(self, iteration_max):
    """Reproduces the crash and prints the stacktrace."""

    logger.info('Reproducing...')

    iterations = 1
    while iterations <= iteration_max:
      _, output = self.reproduce_crash()

      print
      logger.info(output)

      new_crash_state, new_crash_type = self.get_stacktrace_info(output)

      logger.info(
          'New crash type: %s\n'
          'New crash state:\n  %s\n\n'
          'Original crash type: %s\n'
          'Original crash state:\n  %s\n',
          new_crash_type, '\n  '.join(new_crash_state), self.crash_type,
          '\n  '.join(self.crash_state))

      # The crash signature validation is intentionally forgiving.
      if is_similar(
          new_crash_type, new_crash_state, self.crash_type, self.crash_state):
        logger.info('The stacktrace seems similar to the original stacktrace.')
        return True
      else:
        logger.info("The stacktrace doesn't match the original stacktrace.")
        logger.info('Try again (%d times). Press Ctrl+C to stop trying to '
                    'reproduce.', iterations)
      iterations += 1
      time.sleep(3)
    sys.exit(1)


class LibfuzzerJobReproducer(BaseReproducer):
  """A reproducer for libfuzzer job types."""

  def pre_build_steps(self):
    """Steps to run before building."""
    args = deserialize_libfuzzer_args(self.args)
    maybe_fix_dict_args(args, os.path.dirname(self.binary_path))
    self.args = serialize_libfuzzer_args(args)

    super(LibfuzzerJobReproducer, self).pre_build_steps()


class Blackbox(object):
  """Run commands within a virtual display using blackbox window manager."""

  def __init__(self, disable=False):
    self.disable_blackbox = disable

  def __enter__(self):
    if self.disable_blackbox:
      return None

    self.display = xvfbwrapper.Xvfb(width=1280, height=1024)
    self.display.start()
    for i in self.display.xvfb_cmd:
      if i.startswith(':'):
        display_name = i
        break

    logger.info('Starting the blackbox window manager in a virtual display.')
    try:
      self.blackbox = common.start_execute_delay(
          'blackbox', '', '.', {'DISPLAY': display_name})
      self.server = common.start_execute_delay(
          'x11vnc', '-localhost -forever -display %s' % display_name, '.', {})
      self.viewer = common.start_execute_delay(
          'vncviewer', 'localhost', '.', {'DISPLAY': ':0.0'}, delay=5)
    except OSError, e:
      if str(e) == '[Errno 2] No such file or directory':
        raise common.BlackboxNotInstalledError
      raise

    return display_name

  def __exit__(self, unused_type, unused_value, unused_traceback):
    if self.disable_blackbox:
      return
    self.viewer.kill()
    self.server.kill()
    self.blackbox.kill()
    self.display.stop()


class LinuxChromeJobReproducer(BaseReproducer):
  """Adds and extre pre-build step to BaseReproducer."""

  def get_process_ids(self, process_id, recursive=True):
    """Return list of pids for a process and its descendants."""

    # Try to find the running process.
    if not psutil.pid_exists(process_id):
      return []

    pids = [process_id]
    try:
      psutil_handle = psutil.Process(process_id)
      children = psutil_handle.children(recursive=recursive)
      for child in children:
        pids.append(child.pid)
    except:
      logger.info('psutil: Process abruptly ended.')
      raise

    return pids

  def xdotool_command(self, command, display_name):
    """Run a command, returning its output."""
    proc = common.start_execute(
        'xdotool %s' % command, os.path.expanduser('~'),
        environment={'DISPLAY': display_name})

    common.wait_execute(proc, exit_on_error=False, capture_output=False,
                        print_output=False)

  def find_windows_for_process(self, process_id, display_name):
    """Return visible windows belonging to a process."""
    pids = self.get_process_ids(process_id)
    if not pids:
      return []

    logger.info(
        'Waiting for 20 seconds to ensure all windows appear '
        '(pid=%s, display=%s).', pids, display_name)
    time.sleep(20)

    visible_windows = set()
    for pid in pids:
      _, windows = common.execute(
          ('xdotool search --all --pid %s --onlyvisible --name'
           ' ".*"' % pid), os.path.expanduser('~'),
          environment={'DISPLAY': display_name},
          exit_on_error=False, print_output=False)
      for line in windows.splitlines():
        if not line.isdigit():
          continue
        visible_windows.add(line)

    logger.info('Found windows: %s', visible_windows)
    return visible_windows

  def execute_gesture(self, gesture, window, display_name):
    """Executes a specific gesture."""

    gesture_type, gesture_cmd = gesture.split(',')
    if gesture_type == 'windowsize':
      self.xdotool_command('%s %s %s' % (gesture_type, window, gesture_cmd),
                           display_name)
    else:
      self.xdotool_command('%s -- %s' % (gesture_type, gesture_cmd),
                           display_name)

  def run_gestures(self, proc, display_name):
    """Executes all required gestures."""

    time.sleep(self.gesture_start_time)

    logger.info('Running gestures...')
    windows = self.find_windows_for_process(proc.pid, display_name)
    for _, window in enumerate(windows):
      logger.info('Run gestures on window %s', window)
      self.xdotool_command('windowactivate --sync %s' % window, display_name)

      for gesture in self.gestures:
        logger.debug(gesture)
        self.execute_gesture(gesture, window, display_name)
        time.sleep(0.2)

  def pre_build_steps(self):
    """Steps to run before building."""

    user_profile_dir = '/tmp/clusterfuzz-user-profile-data'
    if os.path.exists(user_profile_dir):
      shutil.rmtree(user_profile_dir)
    user_data_str = ' --user-data-dir=%s' % user_profile_dir
    if user_data_str not in self.args:
      self.args += user_data_str
    super(LinuxChromeJobReproducer, self).pre_build_steps()


  def post_run_symbolize(self, output):
    """Symbolizes non-libfuzzer chrome jobs."""

    asan_symbolizer_location = os.path.join(
        self.source_directory, os.path.join('tools', 'valgrind', 'asan',
                                            'asan_symbolize.py'))
    symbolizer_proxy_location = common.get_resource(
        0755, 'asan_symbolize_proxy.py')
    x = common.start_execute(asan_symbolizer_location, os.path.expanduser('~'),
                             {'LLVM_SYMBOLIZER_PATH': symbolizer_proxy_location,
                              'CHROMIUM_SRC': self.source_directory})
    output += '\0'
    out, _ = x.communicate(input=output)
    return out


  def reproduce_crash(self):
    """Reproduce the crash, running gestures if necessary."""

    self.pre_build_steps()

    if (self.disable_blackbox and
        '--disable-gl-drawing-for-tests' in self.args):
      self.args = self.args.replace('--disable-gl-drawing-for-tests', '')
    elif (not self.disable_blackbox and
          '--disable-gl-drawing-for-tests' not in self.args):
      self.args += ' --disable-gl-drawing-for-tests'

    with Blackbox(self.disable_blackbox) as display_name:
      command = '%s %s %s' % (self.binary_path, self.args, self.testcase_path)

      self.environment['DISPLAY'] = display_name
      self.environment.pop('ASAN_SYMBOLIZER_PATH', None)
      process = common.start_execute(
          command, os.path.dirname(self.binary_path),
          environment=self.environment, preexec_fn=os.setsid)
      if self.gestures:
        self.run_gestures(process, display_name)
      err, out = common.wait_execute(process, exit_on_error=False, timeout=15)
      return err, self.post_run_symbolize(out)
