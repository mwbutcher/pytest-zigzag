# -*- coding: utf-8 -*-

# ======================================================================================================================
# Imports
# ======================================================================================================================
from __future__ import absolute_import
import os
import re
import pytest
from json import loads
from datetime import datetime
# noinspection PyPackageRequirements
from zigzag.zigzag import ZigZag
from pkg_resources import resource_stream
from jsonschema import validate, ValidationError
from pytest_zigzag.session_messages import SessionMessages

__version__ = '0.2.0'

# ======================================================================================================================
# Globals
# ======================================================================================================================
SESSION_MESSAGES = SessionMessages()
TEST_STEPS_MARK = 'test_case_with_steps'
ZZ_WARN_MESSAGE = "ZigZag will not attempt upload, '--zigzag' and '--qtest-project-id' must be specified together."


# ======================================================================================================================
# Functions: Private
# ======================================================================================================================
def _capture_marks(items, mark_names):
    """Add XML properties group to each 'testcase' element that captures the specified marks.

    Args:
        items (list(_pytest.nodes.Item)): List of item objects.
        mark_names (list(str)): A list of marks to capture and record in JUnitXML for each 'testcase'.
    """

    for item in items:
        # If item is in a class then check to see if this item is a test step or test case.
        item.user_properties.append(('test_step', 'true' if item.get_closest_marker(TEST_STEPS_MARK) else 'false'))
        for mark_name in mark_names:
            for marker in item.iter_markers(mark_name):
                for arg in marker.args:
                    item.user_properties.append((marker.name, arg))


def _capture_ci_environment(session):
    """Capture the CI environment variables for the current session using the scheme specified by the user.

    Args:
        session (_pytest.main.Session): The pytest session object
    """

    if session.config.pluginmanager.hasplugin('junitxml'):
        junit_xml_config = getattr(session.config, '_xml', None)

        highest_precedence = None

        if junit_xml_config:
            # Determine the config option that we should use
            if _get_option_of_highest_precedence(session.config, 'config_file'):
                highest_precedence = _get_option_of_highest_precedence(session.config, 'config_file')
            if _get_option_of_highest_precedence(session.config, 'pytest-config'):
                highest_precedence = _get_option_of_highest_precedence(session.config, 'pytest-config')
            if not highest_precedence:
                highest_precedence = "./pytest_zigzag/data/configs/default-config.json"

            # Load config
            config_dict = _load_config_file(highest_precedence)

            # Record environment variables in JUnitXML global properties

            for env_var in config_dict['environment_variables']:
                junit_xml_config.add_global_property(env_var,
                                                     os.getenv(env_var,
                                                               config_dict['environment_variables'][env_var]))


def _get_option_of_highest_precedence(config, option_name):
    """looks in the config and returns the option of the highest precedence
    This assumes that there are options and flags that are equivalent

    Args:
        config (_pytest.config.Config): The pytest config object
        option_name (str): The name of the option

    Returns:
        str: The value of the option that is of highest precedence
        None: no value is present
    """

    #  Try to get configs from CLI and ini
    try:
        cli_option = config.getoption("--{}".format(option_name))
    except ValueError:
        cli_option = None
    try:
        ini_option = config.getini(option_name)
    except ValueError:
        ini_option = None

    highest_precedence = cli_option or ini_option
    return highest_precedence


def _validate_qtest_token(token):
    return token if re.match("^[a-zA-Z0-9]+$", token) else ""


def _load_config_file(config_file):
    """Validate and load the contents of a 'pytest-zigzag' config file into memory.

    Args:
        config_file (str): The path to a pytest_zigzag config file.

    Returns:
        config_dict (dict): A dictionary of property names and associated values.
    """

    config_dict = {}
    schema = loads(resource_stream('pytest_zigzag', 'data/schema/pytest-zigzag-config.schema.json').read().decode())

    try:
        with open(config_file, 'r') as f:
            config_dict = loads(f.read())
    except (OSError, IOError):
        pytest.exit("Failed to load '{}' config file!".format(config_file), returncode=1)
    except ValueError as e:
        pytest.exit("The '{}' config file is not valid JSON: {}".format(config_file, str(e)), returncode=1)

    # Validate config
    try:
        validate(config_dict, schema)
    except ValidationError as e:
        pytest.exit("Config file '{}' does not comply with schema: {}".format(config_file, str(e)), returncode=1)

    return config_dict


# ======================================================================================================================
# Hooks
# ======================================================================================================================
@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session):
    """This hook is used by pytest to build the junit XML
    Using ZigZag as a library we upload in the pytest runtime

    Args:
        session (_pytest.main.Session): The pytest session object
    """

    SESSION_MESSAGES.drain()  # need to reset this on every pass through this hook
    if session.config.pluginmanager.hasplugin('junitxml'):
        zz_option = _get_option_of_highest_precedence(session.config, 'zigzag')
        qtest_project_id = _get_option_of_highest_precedence(session.config, 'qtest-project-id')
        if zz_option and qtest_project_id:
            try:
                junit_file_path = getattr(session.config, '_xml', None).logfile
                # noinspection PyTypeChecker
                # validate token
                token = _validate_qtest_token(os.environ['QTEST_API_TOKEN'])
                zz = ZigZag(junit_file_path, token, qtest_project_id, None)
                job_id = zz.upload_test_results()
                SESSION_MESSAGES.append("ZigZag upload was successful!")
                SESSION_MESSAGES.append("Queue Job ID: {}".format(job_id))
            except Exception as e:  # we want this super broad so we dont break test execution
                SESSION_MESSAGES.append('The ZigZag upload was not successful')
                SESSION_MESSAGES.append("Original error message:\n\n{}".format(str(e)))


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter):
    """Use this hook to add what we did to the terminal report"""

    for message in SESSION_MESSAGES:
        terminalreporter.write_line(message)


@pytest.hookimpl(tryfirst=True)
def pytest_runtestloop(session):
    """Add XML properties group to the 'testsuite' element that captures the values for specified environment variables.

    Args:
        session (_pytest.main.Session): The pytest session object
    """

    if session.config.pluginmanager.hasplugin('junitxml'):
        junit_xml_config = getattr(session.config, '_xml', None)

        if junit_xml_config:
            _capture_ci_environment(session)


def pytest_collection_modifyitems(items):
    """Called after collection has been performed, may filter or re-order the items in-place.

    Args:
        items (list(_pytest.nodes.Item)): List of item objects.
    """

    _capture_marks(items, ('test_id', 'jira'))


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Add XML properties group to the 'testcase' element that captures start time in UTC. Also, skip test cases
    in a class where the previous test case failed.

    Args:
        item (_pytest.nodes.Item): An item object.
    """

    now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    item.user_properties.append(('start_time', now))
    item.user_properties.append(('end_time', now))  # will override if we get to teardown

    if "test_case_with_steps" in item.keywords and 'setup' not in item.name and 'teardown' not in item.name:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.skip("because previous test failed: {}".format(previousfailed.name))


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item):
    """Add XML properties group to the 'testcase' element that captures start time in UTC.

    Args:
        item (_pytest.nodes.Item): An item object.
    """

    now_tup = ('end_time', datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))
    position = None

    # find the position of end_time tuple
    for n, tup in enumerate(item.user_properties):
        if tup[0] == 'end_time':
            position = n

    if position is not None:
        item.user_properties[position] = now_tup
    else:
        item.user_properties.append(now_tup)


def pytest_addoption(parser):
    """Adds a config option to pytest

    Args:
        parser (_pytest.config.Parser): A parser object
    """

    config_option = "pytest-config"
    config_option_help = "A config file path to be used for the parser."
    parser.addini(config_option, config_option_help)
    parser.addoption("--{}".format(config_option), help=config_option_help)

    config_option = "config_file"
    config_option_help = "The path to a json config file."
    parser.addini(config_option, config_option_help)
    parser.addoption("--{}".format(config_option), help=config_option_help)

    # options related to publishing
    zigzag_help = 'Enable automatic publishing of test results using ZigZag'
    parser.addini('zigzag', zigzag_help, type='bool', default=False)
    parser.addoption('--zigzag', help=zigzag_help, action="store_true", default=False)

    project_help = 'The target project ID to use as a destination for test results published by ZigZag'
    parser.addini('qtest-project-id', project_help, default=None)
    parser.addoption('--qtest-project-id', help=project_help, default=None)


def pytest_configure(config):
    """Allows plugins and conftest files to perform initial configuration.

    This hook is called for every plugin and initial conftest file after command line options have been parsed.

    After that, the hook is called for other conftest files as they are imported.

    Args:
        config (_pytest.config.Config) a config object
    """

    zz = _get_option_of_highest_precedence(config, 'zigzag')
    qtpid = _get_option_of_highest_precedence(config, 'qtest-project-id')

    if any([zz, qtpid]) and not all([zz, qtpid]):
        config.warn(101, ZZ_WARN_MESSAGE)


def pytest_runtest_makereport(item, call):
    """Re-write the report concerning test cases with steps so it looks correct.

    Args:
        item (_pytest.nodes.Item): An item object.
        call (_pytest.runner.CallInfo): A call info object.
    """

    if "test_case_with_steps" in item.keywords:
        if call.excinfo is not None:
            parent = item.parent
            parent._previousfailed = item
