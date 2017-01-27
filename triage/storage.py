from .utils import upload_object_to_key, key_exists, model_cache_key, download_object
import os
import pickle
import pandas
import yaml


class ModelStorageEngine(object):
    def __init__(self, project_path):
        self.project_path = project_path

    def get_store(self, model_hash):
        pass


class Store(object):
    def __init__(self, path):
        self.path = path

    def exists(self):
        pass

    def load(self):
        pass


class S3Store(Store):
    def exists(self):
        key_exists(self.path)

    def write(self, obj):
        upload_object_to_key(obj, self.path)

    def load(self):
        return download_object(self.path)


class FSStore(Store):
    def exists(self):
        return os.path.isfile(self.path)

    def write(self, obj):
        with open(self.path, 'w+b') as f:
            pickle.dump(obj, f)

    def load(self):
        with open(self.path, 'rb') as f:
            return pickle.load(f)


class S3ModelStorageEngine(ModelStorageEngine):
    def __init__(self, s3_conn, *args, **kwargs):
        super(S3ModelStorageEngine, self).__init__(*args, **kwargs)
        self.s3_conn = s3_conn

    def get_store(self, model_hash):
        return S3Store(model_cache_key(
            self.project_path,
            model_hash,
            self.s3_conn
        ))


class FSModelStorageEngine(ModelStorageEngine):
    def get_store(self, model_hash):
        return FSStore('/'.join([
            self.project_path,
            'trained_models',
            model_hash
        ]))


class MatrixStore(object):
    matrix = None
    metadata = None
    _labels = None

    def labels(self):
        if self._labels is not None:
            return self._labels
        else:
            self._labels = self.matrix.pop(self.metadata['label_name'])
            return self._labels


class MettaMatrixStore(MatrixStore):
    def __init__(self, matrix_path, metadata_path):
        self.matrix = pandas.read_hdf(matrix_path)
        with open(metadata_path) as f:
            self.metadata = yaml.load(f)


class InMemoryMatrixStore(MatrixStore):
    def __init__(self, matrix, metadata):
        self.matrix = matrix
        self.metadata = metadata
