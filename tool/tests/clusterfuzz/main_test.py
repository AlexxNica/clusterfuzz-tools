"""Tests the module that parses and executes commands."""
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

import unittest
import mock

from tool.clusterfuzz import main
from shared import helpers


class MainTest(unittest.TestCase):
  """Test main."""

  def setUp(self):
    helpers.patch(self, [
        'tool.clusterfuzz.commands.reproduce.execute',
        'tool.clusterfuzz.local_logging.start_loggers'
    ])

  def test_parse_reproduce(self):
    """Test parse reproduce command."""
    main.execute(['reproduce', '1234'])
    main.execute(['reproduce', '1234', '-j', '25', '--current'])
    main.execute(['reproduce', '1234', '--disable-goma', '--build', 'download'])
    main.execute(['reproduce', '1234', '--current', '--build', 'standalone'])
    main.execute(['reproduce', '1234', '--build', 'chromium', '-i', '500'])
    main.execute(['reproduce', '1234', '--disable-gclient-commands'])

    self.mock.start_loggers.assert_has_calls([mock.call()])
    self.mock.execute.assert_has_calls([
        mock.call(build='chromium', current=False,
                  disable_gclient_commands=False, disable_goma=False,
                  j=None, testcase_id='1234', iterations=10),
        mock.call(build='chromium', current=True,
                  disable_gclient_commands=False, disable_goma=False,
                  j=25, testcase_id='1234', iterations=10),
        mock.call(build='download', current=False,
                  disable_gclient_commands=False, disable_goma=True,
                  j=None, testcase_id='1234', iterations=10),
        mock.call(build='standalone', current=True,
                  disable_gclient_commands=False, disable_goma=False,
                  j=None, testcase_id='1234', iterations=10),
        mock.call(build='chromium', current=False,
                  disable_gclient_commands=False, disable_goma=False,
                  j=None, testcase_id='1234', iterations=500),
        mock.call(build='chromium', current=False,
                  disable_gclient_commands=True, disable_goma=False,
                  j=None, testcase_id='1234', iterations=10)])
