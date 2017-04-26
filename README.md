ClusterFuzz tools
=================================

Status: Early prototype phase

[![CircleCI](https://circleci.com/gh/google/clusterfuzz-tools/tree/master.svg?style=shield)](https://circleci.com/gh/google/clusterfuzz-tools/tree/master)
[![Coverage Status](https://coveralls.io/repos/github/google/clusterfuzz-tools/badge.svg?branch=master)](https://coveralls.io/github/google/clusterfuzz-tools?branch=master)

The tools supports various tasks (e.g. reproduce a crash locally)
needed by ClusterFuzz's users.

Currently, it supports reproducing a crash locally. In the future, it will
support uploading a fuzzer, tailing fuzzer log, and uploading a testcase.


Requirement
---------------

* [gsutil](https://cloud.google.com/storage/docs/gsutil_install)
* Blackbox, vncviewer, and x11vnc. You can install it with `sudo apt-get install blackbox vncviewer x11vnc`.


Installation
-----------------

ClusterFuzz tools is a single binary file built with [Pex](https://github.com/pantsbuild/pex).
Therefore, you can simply copy the binary and run it.


For Goobuntu:

1. Run `prodaccess`
2. Run `/google/data/ro/teams/clusterfuzz-tools/releases/clusterfuzz reproduce -h`

For others:

1. Download [the latest stable version](https://storage.cloud.google.com/clusterfuzz-tools)
2. Run `clusterfuzz-<version>.pex reproduce -h`


Usage
------

See `<binary> reproduce --help`. Run `<binary> reproduce [testcase-id]`

Here's the workflow (we think) might be appropriate when fixing a bug:

1. Run `<binary> reproduce [testcase-id]`
2. Make a new branch and make a code change
3. Run against the code change with `<binary> reproduce [testcase-id] --current`
4. If the crash doesn’t occur anymore, it means your code change fixes the crash


Develop
------------

1. `./pants -V` to bootstrap [Pants](http://www.pantsbuild.org/)
2. Run the tool's tests: `./pants test --coverage=1 tool:test`
3. Run the ci's tests: `./pants test --coverage=1 ci/continuous_integration:test`
4. Run the tool binary: `./pants run tool:clusterfuzz -- reproduce -h`


Deploy CI
------------

1. Build the CI Pex binary: `./pants binary ci/continuous_integration:ci`
2. TODO(everestmz): Please fill in the ansible command.


Publish
----------

We publish our binary to 2 places: Cloud Storage (for public) and X20 (for Googlers).

1. Increment the version number in `tool/clusterfuzz/resources/VERSION`
2. Create and merge a pull request to increase the version number
3. Set the new version in the env: `export VERSION=<version>`.
4. Build the Pex binary: `./pants binary tool:clusterfuzz-$VERSION`
5. Upload to our public storage: `gsutil cp dist/clusterfuzz-$VERSION.pex gs://clusterfuzz-tools/`
6. Make the link public: `gsutil acl set public-read gs://clusterfuzz-tools/clusterfuzz-$VERSION.pex`
7. Copy to X20: `cp dist/clusterfuzz-$VERSION.pex /google/data/rw/teams/clusterfuzz-tools/releases/`
8. Change permission: `chmod 775 /google/data/rw/teams/clusterfuzz-tools/releases/clusterfuzz-$VERSION.pex`
9. Symlink:
  * Release: `ln -sf /google/data/rw/teams/clusterfuzz-tools/releases/clusterfuzz-$VERSION.pex /google/data/rw/teams/clusterfuzz-tools/releases/clusterfuzz`
  * Release Candidate: `ln -sf /google/data/rw/teams/clusterfuzz-tools/releases/clusterfuzz-$VERSION.pex /google/data/rw/teams/clusterfuzz-tools/releases/clusterfuzz-rc`

10. Confirm it with: `ls -l /google/data/rw/teams/clusterfuzz-tools/releases/clusterfuzz*`
11. Test by running: `/google/data/ro/teams/clusterfuzz-tools/releases/clusterfuzz reproduce -h`
12. Tag the current version with `git tag -a $VERSION -m "Version $VERSION"`
13. Push the tag `git push --tags`

