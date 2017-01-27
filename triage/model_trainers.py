from sklearn.grid_search import ParameterGrid
from sqlalchemy.orm import sessionmaker
from .db import Model, FeatureImportance
import importlib
import json
import logging
import yaml


def get_feature_importances(model):
    """
    Get feature importances (from scikit-learn) of trained model.

    Args:
        model: Trained model

    Returns:
        Feature importances, or failing that, None
    """

    try:
        return model.feature_importances_
    except:
        pass
    try:
        # Must be 1D for feature importance plot
        if len(model.coef_) <= 1:
            return model.coef_[0]
        else:
            return model.coef_
    except:
        pass
    return None


class SimpleModelTrainer(object):
    """Trains a series of classifiers using the same training set
    Args:
        project_path (string) path to project folder on s3,
            under which to cache model pickles
        s3_conn (boto3.s3.connection)
        db_engine (sqlalchemy.engine)
    """
    def __init__(
        self,
        project_path,
        model_storage_engine,
        matrix_store,
        db_engine=None
    ):
        self.project_path = project_path
        self.model_storage_engine = model_storage_engine
        self.matrix_store = matrix_store
        self.db_engine = db_engine
        if self.db_engine:
            self.sessionmaker = sessionmaker(bind=self.db_engine)

    def _model_hash(self, class_path, parameters):
        """Generates a unique identifier for a trained model
        based on attributes of the model that together define
        equivalence; in other words, if we train a second model with these
        same attributes there would be no reason to keep the old one)

        Args:
        class_path (string): a full class path for the classifier
        parameters (dict): all hyperparameters to be passed to the classifier

        Returns: (string) a unique identifier
        """
        unique = {
            'className': class_path,
            'parameters': parameters,
            'project_path': self.project_path,
            'training_metadata': self.matrix_store.metadata
        }
        return hex(hash(json.dumps(unique, sort_keys=True)))

    def _generate_model_configs(self, model_config):
        """Flattens a model/parameter grid configuration into individually
        trainable model/parameter pairs

        Yields: (tuple) classpath and parameters
        """
        for class_path, parameter_config in model_config.items():
            for parameters in ParameterGrid(parameter_config):
                yield class_path, parameters

    def _train(self, class_path, parameters):
        """Fit a model to a training set. Works on any modeling class that
        is available in this package's environment and implements .fit

        Args:
            class_path (string) A full classpath to the model class
            parameters (dict) hyperparameters to give to the model constructor
            train_matrix (pandas.DataFrame) the training matrix including label

        Returns:
            tuple of (fitted model, list of column names without label)
        """
        module_name, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        instance = cls(**parameters)
        y = self.matrix_store.labels()

        return instance.fit(self.matrix_store.matrix, y), self.matrix_store.matrix.columns

    def _write_model_to_db(
        self,
        class_path,
        parameters,
        feature_names,
        model_hash,
        trained_model
    ):
        """Writes model and feature importance data to a database

        Args:
            class_path (string) A full classpath to the model class
            parameters (dict) hyperparameters to give to the model constructor
            feature_names (list) feature names in order given to model
            model_hash (string) a unique id for the model
            trained_model (object) a trained model object
        """
        session = self.sessionmaker()
        model = Model(
            model_hash=model_hash,
            model_type=class_path,
            model_parameters=parameters
        )
        session.add(model)

        for feature_index, importance in \
                enumerate(get_feature_importances(trained_model)):
            feature_importance = FeatureImportance(
                model=model,
                feature_importance=importance,
                feature=feature_names[feature_index],
            )
            session.add(feature_importance)
        session.commit()
        return model.model_id

    def _train_and_store_model(
        self,
        class_path,
        parameters,
        model_hash,
        model_store
    ):
        """Train a model, cache it in s3, and write metadata to a database

        Args:
            class_path (string) A full classpath to the model class
            parameters (dict) hyperparameters to give to the model constructor
            model_hash (string) a unique id for the model
            cache_key (boto3.s3.Object) the s3 key in which to store the model

        Returns: (int) a database id for the model
        """
        trained_model, feature_names = self._train(
            class_path,
            parameters,
        )
        logging.info('Trained model')
        model_store.write(trained_model)
        logging.info('Cached model')
        model_id = self._write_model_to_db(
            class_path,
            parameters,
            feature_names,
            model_hash,
            trained_model
        )
        logging.info('Wrote model to db')
        return model_id

    def train_models(
        self,
        model_config,
        replace=False
    ):
        """Train and store configured models

        Args:
            model_config (dict) of format {classpath: hyperparameter dicts}
                example: { 'sklearn.ensemble.RandomForestClassifier': {
                    'n_estimators': [1,10,100,1000,10000],
                    'max_depth': [1,5,10,20,50,100],
                    'max_features': ['sqrt','log2'],
                    'min_samples_split': [2,5,10]
                } }
            replace (optional, False): whether to replace already cached models

        Returns:
            (list) of model ids
        """
        model_ids = []
        for class_path, parameters in self._generate_model_configs(model_config):
            model_hash = self._model_hash(class_path, parameters)
            model_store = self.model_storage_engine.get_store(model_hash)
            if replace or not model_store.exists():
                logging.info('Training %s/%s', class_path, parameters)
                model_id = self._train_and_store_model(
                    class_path,
                    parameters,
                    model_hash,
                    model_store
                )
                model_ids.append(model_id)
            else:
                logging.info('Skipping %s/%s', class_path, parameters)

        return model_ids
