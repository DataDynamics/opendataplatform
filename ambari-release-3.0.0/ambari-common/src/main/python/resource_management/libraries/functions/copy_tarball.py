#!/usr/bin/env python3
"""
Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements.  See the NOTICE file
distributed with this work for additional information
regarding copyright ownership.  The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License.  You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

__all__ = ["copy_to_hdfs", "get_sysprep_skip_copy_tarballs_hdfs"]

import os
import tempfile
import re

from resource_management.libraries.script.script import Script
from resource_management.libraries.functions import component_version
from resource_management.libraries.functions import lzo_utils
from resource_management.libraries.functions.default import default
from resource_management.core import shell
from resource_management.core import sudo
from resource_management.core.logger import Logger
from resource_management.core.exceptions import Fail
from resource_management.core.resources.system import Directory
from resource_management.core.resources.system import Execute
from resource_management.libraries.functions import (
  stack_tools,
  stack_features,
  stack_select,
)
from resource_management.libraries.functions import tar_archive

STACK_NAME_PATTERN = "{{ stack_name }}"
STACK_ROOT_PATTERN = "{{ stack_root }}"
STACK_VERSION_PATTERN = "{{ stack_version }}"
LIB_DIR = "usr/lib"


def _prepare_tez_tarball():
  """
  Prepares the Tez tarball by adding the Hadoop native libraries found in the mapreduce tarball.
  It's very important to use the version of mapreduce which matches tez here.
  Additionally, this will also copy native LZO to the tez tarball if LZO is enabled and the
  GPL license has been accepted.
  :return:  the full path of the newly created tez tarball to use
  """
  import tempfile

  Logger.info("Preparing the Tez tarball...")

  # get the mapreduce tarball which matches the version of tez
  # tez installs the mapreduce tar, so it should always be present
  _, mapreduce_source_file, _, _ = get_tarball_paths("mapreduce")
  _, tez_source_file, _, _ = get_tarball_paths("tez")

  temp_dir = Script.get_tmp_dir()

  # create the temp staging directories ensuring that non-root agents using tarfile can work with them
  mapreduce_temp_dir = tempfile.mkdtemp(prefix="mapreduce-tarball-", dir=temp_dir)
  tez_temp_dir = tempfile.mkdtemp(prefix="tez-tarball-", dir=temp_dir)
  sudo.chmod(mapreduce_temp_dir, 0o777)
  sudo.chmod(tez_temp_dir, 0o777)

  Logger.info(f"Extracting {mapreduce_source_file} to {mapreduce_temp_dir}")
  tar_archive.untar_archive(mapreduce_source_file, mapreduce_temp_dir)

  Logger.info(f"Extracting {tez_source_file} to {tez_temp_dir}")
  tar_archive.untar_archive(tez_source_file, tez_temp_dir)

  hadoop_lib_native_dir = os.path.join(mapreduce_temp_dir, "hadoop", "lib", "native")
  tez_lib_dir = os.path.join(tez_temp_dir, "lib")

  if not os.path.exists(hadoop_lib_native_dir):
    raise Fail(
      f"Unable to seed the Tez tarball with native libraries since the source Hadoop native lib directory {hadoop_lib_native_dir} does not exist"
    )

  if not os.path.exists(tez_lib_dir):
    raise Fail(
      f"Unable to seed the Tez tarball with native libraries since the target Tez lib directory {tez_lib_dir} does not exist"
    )

  # copy native libraries from hadoop to tez
  Execute(("cp", "-a", hadoop_lib_native_dir, tez_lib_dir), sudo=True)

  # if enabled, LZO GPL libraries must be copied as well
  if lzo_utils.should_install_lzo():
    stack_root = Script.get_stack_root()
    service_version = component_version.get_component_repository_version(
      service_name="TEZ"
    )

    # some installations might not have Tez, but MapReduce2 should be a fallback to get the LZO libraries from
    if service_version is None:
      Logger.warning(
        "Tez does not appear to be installed, using the MapReduce version to get the LZO libraries"
      )
      service_version = component_version.get_component_repository_version(
        service_name="MAPREDUCE2"
      )

    hadoop_lib_native_lzo_dir = os.path.join(
      stack_root, service_version, "hadoop", "lib", "native"
    )

    if not sudo.path_isdir(hadoop_lib_native_lzo_dir):
      Logger.warning(
        f"Unable to located native LZO libraries at {hadoop_lib_native_lzo_dir}, falling back to hadoop home"
      )
      hadoop_lib_native_lzo_dir = os.path.join(
        stack_root, "current", "hadoop-client", "lib", "native"
      )

    if not sudo.path_isdir(hadoop_lib_native_lzo_dir):
      raise Fail(
        f"Unable to seed the Tez tarball with native libraries since LZO is enabled but the native LZO libraries could not be found at {hadoop_lib_native_lzo_dir}"
      )

    Execute(("cp", "-a", hadoop_lib_native_lzo_dir, tez_lib_dir), sudo=True)

  # ensure that the tez/lib directory is readable by non-root (which it typically is not)
  Directory(tez_lib_dir, mode=0o755, cd_access="a", recursive_ownership=True)

  # create the staging directory so that non-root agents can write to it
  tez_native_tarball_staging_dir = os.path.join(temp_dir, "tez-native-tarball-staging")
  if not os.path.exists(tez_native_tarball_staging_dir):
    Directory(
      tez_native_tarball_staging_dir,
      mode=0o777,
      cd_access="a",
      create_parents=True,
      recursive_ownership=True,
    )

  tez_tarball_with_native_lib = os.path.join(
    tez_native_tarball_staging_dir, "tez-native.tar.gz"
  )
  Logger.info(f"Creating a new Tez tarball at {tez_tarball_with_native_lib}")
  tar_archive.archive_dir_via_temp_file(tez_tarball_with_native_lib, tez_temp_dir)

  # ensure that the tarball can be read and uploaded
  sudo.chmod(tez_tarball_with_native_lib, 0o744)

  # cleanup
  sudo.rmtree(mapreduce_temp_dir)
  sudo.rmtree(tez_temp_dir)

  return tez_tarball_with_native_lib


def _prepare_mapreduce_tarball():
  """
  Prepares the mapreduce tarball by including the native LZO libraries if necessary. If LZO is
  not enabled or has not been opted-in, then this will do nothing and return the original
  tarball to upload to HDFS.
  :return:  the full path of the newly created mapreduce tarball to use or the original path
  if no changes were made
  """
  # get the mapreduce tarball to crack open and add LZO libraries to
  _, mapreduce_source_file, _, _ = get_tarball_paths("mapreduce")

  if not lzo_utils.should_install_lzo():
    return mapreduce_source_file

  Logger.info("Preparing the mapreduce tarball with native LZO libraries...")

  temp_dir = Script.get_tmp_dir()

  # create the temp staging directories ensuring that non-root agents using tarfile can work with them
  mapreduce_temp_dir = tempfile.mkdtemp(prefix="mapreduce-tarball-", dir=temp_dir)
  sudo.chmod(mapreduce_temp_dir, 0o777)

  # calculate the source directory for LZO
  hadoop_lib_native_source_dir = os.path.join(
    os.path.dirname(mapreduce_source_file), "lib", "native"
  )
  if not sudo.path_exists(hadoop_lib_native_source_dir):
    raise Fail(
      f"Unable to seed the mapreduce tarball with native LZO libraries since the source Hadoop native lib "
      f"directory {hadoop_lib_native_source_dir} does not exist"
    )

  Logger.info(f"Extracting {mapreduce_source_file} to {mapreduce_temp_dir}")
  tar_archive.untar_archive(mapreduce_source_file, mapreduce_temp_dir)

  mapreduce_lib_dir = os.path.join(mapreduce_temp_dir, "hadoop", "lib")

  # copy native libraries from source hadoop to target
  Execute(("cp", "-af", hadoop_lib_native_source_dir, mapreduce_lib_dir), sudo=True)

  # ensure that the hadoop/lib/native directory is readable by non-root (which it typically is not)
  Directory(mapreduce_lib_dir, mode=0o755, cd_access="a", recursive_ownership=True)

  # create the staging directory so that non-root agents can write to it
  mapreduce_native_tarball_staging_dir = os.path.join(
    temp_dir, "mapreduce-native-tarball-staging"
  )
  if not os.path.exists(mapreduce_native_tarball_staging_dir):
    Directory(
      mapreduce_native_tarball_staging_dir,
      mode=0o777,
      cd_access="a",
      create_parents=True,
      recursive_ownership=True,
    )

  mapreduce_tarball_with_native_lib = os.path.join(
    mapreduce_native_tarball_staging_dir, "mapreduce-native.tar.gz"
  )
  Logger.info(
    f"Creating a new mapreduce tarball at {mapreduce_tarball_with_native_lib}"
  )
  tar_archive.archive_dir_via_temp_file(
    mapreduce_tarball_with_native_lib, mapreduce_temp_dir
  )

  # ensure that the tarball can be read and uploaded
  sudo.chmod(mapreduce_tarball_with_native_lib, 0o744)

  # cleanup
  sudo.rmtree(mapreduce_temp_dir)

  return mapreduce_tarball_with_native_lib


# TODO, in the future, each stack can define its own mapping of tarballs
# inside the stack definition directory in some sort of xml file.
# PLEASE DO NOT put this in cluster-env since it becomes much harder to change,
# especially since it is an attribute of a stack and becomes
# complicated to change during a Rolling/Express upgrade.
TARBALL_MAP = {
  "yarn": {
    "dirs": (
      f"{STACK_ROOT_PATTERN}/{STACK_VERSION_PATTERN}/{LIB_DIR}/hadoop-yarn/lib/service-dep.tar.gz",
      f"/{STACK_NAME_PATTERN}/apps/{STACK_VERSION_PATTERN}/yarn/service-dep.tar.gz",
    ),
    "service": "YARN",
  },
  "tez": {
    "dirs": (
      f"{STACK_ROOT_PATTERN}/{STACK_VERSION_PATTERN}/{LIB_DIR}/tez/lib/tez.tar.gz",
      f"/{STACK_NAME_PATTERN}/apps/{STACK_VERSION_PATTERN}/tez/tez.tar.gz",
    ),
    "service": "TEZ",
  },
  "tez_hive2": {
    "dirs": (
      f"{STACK_ROOT_PATTERN}/{STACK_VERSION_PATTERN}/{LIB_DIR}/tez_hive2/lib/tez.tar.gz",
      f"/{STACK_NAME_PATTERN}/apps/{STACK_VERSION_PATTERN}/tez_hive2/tez.tar.gz",
    ),
    "service": "HIVE",
  },
  "hive": {
    "dirs": (
      f"{STACK_ROOT_PATTERN}/{STACK_VERSION_PATTERN}/{LIB_DIR}/hive/hive.tar.gz",
      f"/{STACK_NAME_PATTERN}/apps/{STACK_VERSION_PATTERN}/hive/hive.tar.gz",
    ),
    "service": "HIVE",
  },
  "hadoop_streaming": {
    "dirs": (
      f"{STACK_ROOT_PATTERN}/{STACK_VERSION_PATTERN}/{LIB_DIR}/hadoop-mapreduce/hadoop-streaming.jar",
      f"/{STACK_NAME_PATTERN}/apps/{STACK_VERSION_PATTERN}/mpreduce/hadoop-streaming.jar",
    ),
    "service": "MAPREDUCE2",
  },
  "mapreduce": {
    "dirs": (
      f"{STACK_ROOT_PATTERN}/{STACK_VERSION_PATTERN}/{LIB_DIR}/hadoop/mapreduce.tar.gz",
      f"/{STACK_NAME_PATTERN}/apps/{STACK_VERSION_PATTERN}/mapreduce/mapreduce.tar.gz",
    ),
    "service": "MAPREDUCE2",
    "prepare_function": _prepare_mapreduce_tarball,
  },
  "spark": {
    "dirs": (
      f"{STACK_ROOT_PATTERN}/{STACK_VERSION_PATTERN}/{LIB_DIR}/spark/lib/spark-{STACK_NAME_PATTERN}-assembly.jar",
      f"/{STACK_NAME_PATTERN}/apps/{STACK_VERSION_PATTERN}/spark/spark-{STACK_NAME_PATTERN}-assembly.jar",
    ),
    "service": "SPARK",
  },
  "spark2": {
    "dirs": (
      f"/tmp/spark2/spark2-{STACK_NAME_PATTERN}-yarn-archive.tar.gz",
      f"/{STACK_NAME_PATTERN}/apps/{STACK_VERSION_PATTERN}/spark2/spark2-{STACK_NAME_PATTERN}-yarn-archive.tar.gz",
    ),
    "service": "SPARK2",
  },
  "spark2hive": {
    "dirs": (
      f"/tmp/spark2/spark2-{STACK_NAME_PATTERN}-hive-archive.tar.gz",
      f"/{STACK_NAME_PATTERN}/apps/{STACK_VERSION_PATTERN}/spark2/spark2-{STACK_NAME_PATTERN}-hive-archive.tar.gz",
    ),
    "service": "SPARK2",
  },
}

SERVICE_TO_CONFIG_MAP = {
  "yarn": "yarn-env",
  "tez": "tez-env",
  "hive": "hive-env",
  "mapreduce": "hadoop-env",
  "hadoop_streaming": "mapred-env",
  "tez_hive2": "hive-env",
  "spark": "spark-env",
  "spark2": "spark2-env",
  "spark2hive": "spark2-env",
}


def get_sysprep_skip_copy_tarballs_hdfs():
  host_sys_prepped = default("/ambariLevelParams/host_sys_prepped", False)

  # By default, copy the tarballs to HDFS. If the cluster is sysprepped, then set based on the config.
  sysprep_skip_copy_tarballs_hdfs = False
  if host_sys_prepped:
    sysprep_skip_copy_tarballs_hdfs = default(
      "/configurations/cluster-env/sysprep_skip_copy_tarballs_hdfs", False
    )
  return sysprep_skip_copy_tarballs_hdfs


def get_tarball_paths(
  name,
  use_upgrading_version_during_upgrade=True,
  custom_source_file=None,
  custom_dest_file=None,
):
  """
  For a given tarball name, get the source and destination paths to use.
  :param name: Tarball name
  :param use_upgrading_version_during_upgrade:
  :param custom_source_file: If specified, use this source path instead of the default one from the map.
  :param custom_dest_file: If specified, use this destination path instead of the default one from the map.
  :return: A tuple of (success status, source path, destination path, optional preparation function which is invoked to setup the tarball)
  """
  stack_name = Script.get_stack_name()

  if not stack_name:
    Logger.error(
      f"Cannot copy {str(name)} tarball to HDFS because stack name could not be determined."
    )
    return False, None, None

  if name is None or name.lower() not in TARBALL_MAP:
    Logger.error(
      f"Cannot copy tarball to HDFS because {str(name)} is not supported in stack {str(stack_name)} for this operation."
    )
    return False, None, None

  service = TARBALL_MAP[name.lower()]["service"]

  stack_version = get_current_version(
    service=service,
    use_upgrading_version_during_upgrade=use_upgrading_version_during_upgrade,
  )
  if not stack_version:
    Logger.error(
      f"Cannot copy {str(name)} tarball to HDFS because stack version could be be determined."
    )
    return False, None, None

  stack_root = Script.get_stack_root()
  if not stack_root:
    Logger.error(
      f"Cannot copy {str(name)} tarball to HDFS because stack root could be be determined."
    )
    return False, None, None

  (source_file, dest_file) = TARBALL_MAP[name.lower()]["dirs"]

  if custom_source_file is not None:
    source_file = custom_source_file

  if custom_dest_file is not None:
    dest_file = custom_dest_file

  source_file = source_file.replace(STACK_NAME_PATTERN, stack_name.lower())
  dest_file = dest_file.replace(STACK_NAME_PATTERN, stack_name.lower())

  source_file = source_file.replace(STACK_ROOT_PATTERN, stack_root.lower())
  dest_file = dest_file.replace(STACK_ROOT_PATTERN, stack_root.lower())

  source_file = source_file.replace(STACK_VERSION_PATTERN, stack_version)
  dest_file = dest_file.replace(STACK_VERSION_PATTERN, stack_version)

  prepare_function = None
  if "prepare_function" in TARBALL_MAP[name.lower()]:
    prepare_function = TARBALL_MAP[name.lower()]["prepare_function"]

  return True, source_file, dest_file, prepare_function


def get_current_version(service=None, use_upgrading_version_during_upgrade=True):
  """
  Get the effective version to use to copy the tarballs to.
  :param service: the service name when checking for an upgrade.  made optional for unknown \
    code bases that may be using this function
  :param use_upgrading_version_during_upgrade: True, except when the RU/EU hasn't started yet.
  :return: Version, or False if an error occurred.
  """

  from resource_management.libraries.functions import upgrade_summary

  # get the version for this command
  version = stack_features.get_stack_feature_version(Script.get_config())
  if service is not None:
    version = upgrade_summary.get_target_version(
      service_name=service, default_version=version
    )

  # if there is no upgrade, then use the command's version
  if not Script.in_stack_upgrade() or use_upgrading_version_during_upgrade:
    Logger.info(
      f"Tarball version was calcuated as {version}. Use Command Version: {use_upgrading_version_during_upgrade}"
    )

    return version

  # we're in an upgrade and we need to use an older version
  current_version = stack_select.get_role_component_current_stack_version()
  if service is not None:
    current_version = upgrade_summary.get_source_version(
      service_name=service, default_version=current_version
    )

  if current_version is None:
    Logger.warning(
      "Unable to determine the current version of the component for this command; unable to copy the tarball"
    )
    return False

  return current_version


def _get_single_version_from_stack_select():
  """
  Call "<stack-selector> versions" and return the version string if only one version is available.
  :return: Returns a version string if successful, and None otherwise.
  """
  # Ubuntu returns: "stdin: is not a tty", as subprocess output, so must use a temporary file to store the output.
  tmp_dir = Script.get_tmp_dir()
  tmp_file = os.path.join(tmp_dir, "copy_tarball_out.txt")
  stack_version = None

  out = None
  stack_selector_path = stack_tools.get_stack_tool_path(stack_tools.STACK_SELECTOR_NAME)
  get_stack_versions_cmd = f"{stack_selector_path} versions > {tmp_file}"
  try:
    code, stdoutdata = shell.call(get_stack_versions_cmd, logoutput=True)
    with open(tmp_file, "r+") as file:
      out = file.read()
  except Exception as e:
    Logger.logger.exception(
      f"Could not parse output of {str(tmp_file)}. Error: {str(e)}"
    )
  finally:
    try:
      if os.path.exists(tmp_file):
        os.remove(tmp_file)
    except Exception as e:
      Logger.logger.exception(f"Could not remove file {str(tmp_file)}. Error: {str(e)}")

  if code != 0 or out is None or out == "":
    Logger.error(
      f"Could not verify stack version by calling '{get_stack_versions_cmd}'. Return Code: {str(code)}, Output: {str(out)}."
    )
    return None

  matches = re.findall(r"([\d\.]+(?:-\d+)?)", out)

  if matches and len(matches) == 1:
    stack_version = matches[0]
  elif matches and len(matches) > 1:
    Logger.error(
      f"Found multiple matches for stack version, cannot identify the correct one from: {', '.join(matches)}"
    )

  return stack_version


def copy_to_hdfs(
  name,
  user_group,
  owner,
  file_mode=0o444,
  custom_source_file=None,
  custom_dest_file=None,
  force_execute=False,
  use_upgrading_version_during_upgrade=True,
  replace_existing_files=False,
  skip=False,
  skip_component_check=False,
):
  """
  :param name: Tarball name, e.g., tez, hive, pig, sqoop.
  :param user_group: Group to own the directory.
  :param owner: File owner
  :param file_mode: File permission
  :param custom_source_file: Override the source file path
  :param custom_dest_file: Override the destination file path
  :param force_execute: If true, will execute the HDFS commands immediately, otherwise, will defer to the calling function.
  :param use_upgrading_version_during_upgrade: If true, will use the version going to during upgrade. Otherwise, use the CURRENT (source) version.
  :param skip: If true, tarballs will not be copied as the cluster deployment uses prepped VMs.
  :param skip_component_check: If true, will skip checking if a given component is installed on the node for a file under its dir to be copied.
                               This is in case the file is not mapped to a component but rather to a specific location (JDK jar, Ambari jar, etc).
  :return: Will return True if successful, otherwise, False.
  """
  import params

  Logger.info(f"Called copy_to_hdfs tarball: {name}")
  (success, source_file, dest_file, prepare_function) = get_tarball_paths(
    name, use_upgrading_version_during_upgrade, custom_source_file, custom_dest_file
  )

  if not success:
    Logger.error(
      f"Could not copy tarball {str(name)} due to a missing or incorrect parameter."
    )
    return False

  if skip:
    Logger.warning(
      f"Skipping copying {str(source_file)} to {str(dest_file)} for {str(name)} as it is a sys prepped host."
    )
    return True

  if not skip_component_check:
    # Check if service is installed on the cluster to check if a file can be copied into HDFS
    config_name = SERVICE_TO_CONFIG_MAP.get(name)
    config = default("/configurations/" + config_name, None)
    if config is None:
      Logger.info(
        f"{config_name} is not present on the cluster. Skip copying {source_file}"
      )
      return False

  Logger.info(f"Source file: {source_file} , Dest file in HDFS: {dest_file}")

  if not os.path.exists(source_file):
    Logger.error(
      f"WARNING. Cannot copy {str(name)} tarball because file does not exist: {str(source_file)} . "
      "It is possible that this component is not installed on this host."
    )
    return False

  # Because CopyFromLocal does not guarantee synchronization, it's possible for two processes to first attempt to
  # copy the file to a temporary location, then process 2 fails because the temporary file was already created by
  # process 1, so process 2 tries to clean up by deleting the temporary file, and then process 1
  # cannot finish the copy to the final destination, and both fail!
  # For this reason, the file name on the destination must be unique, and we then rename it to the intended value.
  # The rename operation is synchronized by the Namenode.

  # unique_string = str(uuid.uuid4())[:8]
  # temp_dest_file = dest_file + "." + unique_string

  # The logic above cannot be used until fast-hdfs-resource.jar supports the mv command, or it switches
  # to WebHDFS.

  # if there is a function which is needed to prepare the tarball, then invoke it first
  if prepare_function is not None:
    source_file = prepare_function()

  # If the directory already exists, it is a NO-OP
  dest_dir = os.path.dirname(dest_file)
  params.HdfsResource(
    dest_dir, type="directory", action="create_on_execute", owner=owner, mode=0o555
  )

  # If the file already exists, it is a NO-OP
  params.HdfsResource(
    dest_file,
    type="file",
    action="create_on_execute",
    source=source_file,
    group=user_group,
    owner=owner,
    mode=0o444,
    replace_existing_files=replace_existing_files,
  )
  Logger.info(
    f"Will attempt to copy {name} tarball from {source_file} to DFS at {dest_file}."
  )

  # For improved performance, force_execute should be False so that it is delayed and combined with other calls.
  # If still want to run the command now, set force_execute to True
  if force_execute:
    params.HdfsResource(None, action="execute")

  return True
