#!/usr/bin/env python3


import pymongo


class ModelDBException(Exception):
    pass


def push_model(config, db_model):
    if (config.model_db is None or config.model_db.host is None or
            config.model_db.port is None):
        print('warning: ModelDB: unable to push model, no connection '
                'information given')
        # TODO: we could also raise an exception here
        return
    client = pymongo.MongoClient(config.model_db.host, config.model_db.port)
    db = client[config.model_db.db_name]
    collection = db[config.model_db.collection_name]
    try:
        collection.insert_one(db_model)
    except Exception as e:
        raise ModelDBException() from e


