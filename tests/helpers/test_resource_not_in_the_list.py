# -*- coding: utf-8 -*-
import pytest_zigzag.helpers

"""Test cases for the 'resource_not_in_the_list' helper function."""


def test_true(mocker):
    """Verify resource_not_in_the_list returns True when _resource_in_list resolves
    to True."""

    mocker.patch('pytest_zigzag.helpers._resource_in_list', return_value=True)

    assert pytest_zigzag.helpers.resource_not_in_the_list('server', 'myserver',
                                                          'host')


def test_false(mocker):
    """Verify resource_not_in_the_list returns False when _resource_in_list resolves
    to False."""

    mocker.patch('pytest_zigzag.helpers._resource_in_list', return_value=False)

    assert not pytest_zigzag.helpers.resource_not_in_the_list('server', 'myserver',
                                                              'host')
