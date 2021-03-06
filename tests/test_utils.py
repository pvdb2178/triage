from triage.utils import filename_friendly_hash, \
    save_experiment_and_get_hash, \
    sort_predictions_and_labels
from triage.db import ensure_db
from sqlalchemy import create_engine
import testing.postgresql
import datetime
import logging
import re


def test_filename_friendly_hash():
    data = {
        'stuff': 'stuff',
        'other_stuff': 'more_stuff',
        'a_datetime': datetime.datetime(2015, 1, 1),
        'a_date': datetime.date(2016, 1, 1),
        'a_number': 5.0
    }
    output = filename_friendly_hash(data)
    assert isinstance(output, str)
    assert re.match('^[\w]+$', output) is not None

    # make sure ordering keys differently doesn't change the hash
    new_output = filename_friendly_hash({
        'other_stuff': 'more_stuff',
        'stuff': 'stuff',
        'a_datetime': datetime.datetime(2015, 1, 1),
        'a_date': datetime.date(2016, 1, 1),
        'a_number': 5.0
    })
    assert new_output == output

    # make sure new data hashes to something different
    new_output = filename_friendly_hash({
        'stuff': 'stuff',
        'a_number': 5.0
    })
    assert new_output != output


def test_filename_friendly_hash_stability():
    nested_data = {
        'one': 'two',
        'three': {
            'four': 'five',
            'six': 'seven'
        }
    }
    output = filename_friendly_hash(nested_data)
    # 1. we want to make sure this is stable across different runs
    # so hardcode an expected value
    assert output == '9a844a7ebbfd821010b1c2c13f7391e6'
    other_nested_data = {
        'one': 'two',
        'three': {
            'six': 'seven',
            'four': 'five'
        }
    }
    new_output = filename_friendly_hash(other_nested_data)
    assert output == new_output


def test_save_experiment_and_get_hash():
    # no reason to make assertions on the config itself, use a basic dict
    experiment_config = {'one': 'two'}
    with testing.postgresql.Postgresql() as postgresql:
        engine = create_engine(postgresql.url())
        ensure_db(engine)
        exp_hash = save_experiment_and_get_hash(experiment_config, engine)
        assert isinstance(exp_hash, str)
        new_hash = save_experiment_and_get_hash(experiment_config, engine)
        assert new_hash == exp_hash

def test_sort_predictions_and_labels():
    predictions = [
        0.5,
        0.4,
        0.6,
        0.5,
    ]

    labels = [
        False,
        False,
        True,
        True
    ]

    sorted_predictions, sorted_labels = sort_predictions_and_labels(
        predictions,
        labels,
        8
    )
    assert sorted_predictions == (0.6, 0.5, 0.5, 0.4)
    assert sorted_labels == (True, True, False, False)


    sorted_predictions, sorted_labels = sort_predictions_and_labels(
        predictions,
        labels,
        12345
    )
    assert sorted_predictions == (0.6, 0.5, 0.5, 0.4)
    assert sorted_labels == (True, False, True, False)
