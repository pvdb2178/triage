from .db import Model, Prediction
from sqlalchemy.orm import sessionmaker


class Predictor(object):
    def __init__(self, project_path, model_storage_engine, db_engine):
        """Encapsulates the task of generating predictions on an arbitrary
        dataset and storing the results

        Args:
            project_path (string) a desired fs/s3 project path
            model_storage_engine (triage.storage.ModelStorageEngine)
            db_engine (sqlalchemy.engine)
        """
        self.project_path = project_path
        self.model_storage_engine = model_storage_engine
        self.db_engine = db_engine
        if self.db_engine:
            self.sessionmaker = sessionmaker(bind=self.db_engine)

    def _load_model(self, model_id):
        """Downloads the cached model associated with a given model id

        Args:
            model_id (int) The id of a given model in the database

        Returns:
            A python object which implements .predict()
        """
        model_hash = self.sessionmaker().query(Model).get(model_id).model_hash
        model_store = self.model_storage_engine.get_store(model_hash)
        return model_store.load()

    def _write_to_db(self, model_id, as_of_date, entity_ids, predictions, labels):
        """Writes given predictions to database

        entity_ids, predictions, labels are expected to be in the same order

        Args:
            model_id (int) the id of the model associated with the given predictions
            as_of_date (datetime.date) the date the predictions were made 'as of'
            entity_ids (iterable) entity ids that predictions were made on
            predictions (iterable) predicted values
            labels (iterable) labels of prediction set (int) the id of the model to predict based off of
            dataset_path (string)
        """
        session = self.sessionmaker()
        for entity_id, score, label in zip(entity_ids, predictions, labels):
            prediction = Prediction(
                model_id=model_id,
                entity_id=int(entity_id),
                as_of_date=as_of_date,
                entity_score=score,
                label_value=int(label)
            )
            session.add(prediction)
        session.commit()

    def predict(self, model_id, matrix_store):
        """Generate predictions and store them in the database

        Args:
            model_id (int) the id of the trained model to predict based off of

        Returns:
            (numpy.Array) the generated prediction values
        """
        label_name = matrix_store.metadata['label_name']
        model = self._load_model(model_id)
        labels = matrix_store.matrix.pop(label_name)
        as_of_date = matrix_store.metadata['end_time']
        predictions = model.predict(matrix_store.matrix)
        self._write_to_db(model_id, as_of_date, matrix_store.matrix.index, predictions, labels)
        return predictions
