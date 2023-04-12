import os

from pymongo import MongoClient
from pymongo.server_api import ServerApi

class MongoDB():
    """
    Environment Variables:
        MONGODB__PATH
        MONGODB__DBNAME
    """
    client: None
    db: None

    def connect_to_database(self, mongo_path=None, db_name=None):
        mongo_path = mongo_path or os.getenv('MONGODB__PATH')
        db_name = db_name or os.getenv('MONGODB__DBNAME')
        self.client = MongoClient(mongo_path,server_api=ServerApi('1'))
        try:
            self.client.admin.command('ping')
            print("Pinged your deployment. You successfully connected to MongoDB!")
        except Exception as e:
            print(e)
        self.db = self.client[db_name]


mongodb = MongoDB()
