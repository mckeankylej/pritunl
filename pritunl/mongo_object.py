from pritunl.constants import *
from pritunl.exceptions import *
from pritunl.descriptors import *
from pritunl.mongo_dict import MongoDict
from pritunl.mongo_list import MongoList
import bson
import json
import os

class MongoObject(object):
    fields = set()
    fields_default = {}

    def __new__(cls, id=None, doc=None, spec=None, **kwargs):
        mongo_object = object.__new__(cls)
        mongo_object.changed = set()
        mongo_object.id = id

        if id or doc or spec:
            mongo_object.exists = True
            try:
                mongo_object.load(doc=doc, spec=spec)
            except NotFound:
                return None
        else:
            mongo_object.exists = False
            mongo_object.id = str(bson.ObjectId())
        return mongo_object

    def __setattr__(self, name, value):
        if name != 'fields' and name in self.fields:
            if isinstance(value, list) and not isinstance(
                    value, MongoList):
                value = MongoList(value)
            elif isinstance(value, dict) and not isinstance(
                    value, MongoDict):
                value = MongoDict(value)
            else:
                self.changed.add(name)
        object.__setattr__(self, name, value)

    def __getattr__(self, name):
        if name in self.fields:
            if name in self.fields_default:
                return self.fields_default[name]
            return
        raise AttributeError(
            'MongoObject instance has no attribute %r' % name)

    @static_property
    def collection(cls):
        raise TypeError('Database collection must be specified')

    def load(self, doc=None, spec=None):
        if doc and spec:
            raise TypeError('Doc and spec both defined')
        if not doc:
            if not spec:
                spec = {
                    '_id': bson.ObjectId(self.id),
                }
            doc = self.collection.find_one(spec)
            if not doc:
                raise NotFound('Document not found', {
                    'spec': spec,
                })
        doc['id'] = str(doc.pop('_id'))
        for key, value in doc.iteritems():
            if isinstance(value, list):
                value = MongoList(value, changed=False)
            elif isinstance(value, dict):
                value = MongoDict(value, changed=False)
            setattr(self, key, value)

    def export(self):
        doc = self.fields_default.copy()
        doc['_id'] = bson.ObjectId(self.id)
        for field in self.fields:
            if hasattr(self, field):
                doc[field] = getattr(self, field)
        return doc

    def commit(self, fields=None, transaction=None):
        doc = {}
        if fields:
            if isinstance(fields, basestring):
                fields = (fields,)
        elif self.exists:
            fields = self.changed
            for field in self.fields:
                if not hasattr(self, field):
                    continue
                value = getattr(self, field)

                if isinstance(value, (MongoList, MongoDict)):
                    if value.changed:
                        if field in fields:
                            fields.remove(field)
                        doc[field] = value

        if transaction:
            collection = transaction.collection(
                self.collection.collection_name)
        else:
            collection = self.collection

        if fields or doc:
            for field in fields:
                doc[field] = getattr(self, field)
            collection.update({
                '_id': bson.ObjectId(self.id),
            }, {
                '$set': doc,
            }, upsert=True)
        elif not self.exists:
            doc = self.fields_default.copy()
            doc['_id'] = bson.ObjectId(self.id)
            for field in self.fields:
                if hasattr(self, field):
                    doc[field] = getattr(self, field)
            collection.update({
                '_id': bson.ObjectId(self.id),
            }, doc, upsert=True)

        self.exists = True
        self.changed = set()

    def remove(self):
        self.collection.remove(bson.ObjectId(self.id))

    def read_file(self, field, path):
        with open(path, 'r') as field_file:
            setattr(self, field, field_file.read())

    def write_file(self, field, path, chmod=None):
        with open(path, 'w') as field_file:
            if chmod:
                os.chmod(path, chmod)
            field_file.write(getattr(self, field))
