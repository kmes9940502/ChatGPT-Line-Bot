import json
import datetime


class FileStorage:
    def __init__(self, file_name):
        self.fine_name = file_name
        self.history = {}

    def save(self, data):
        self.history.update(data)
        with open(self.fine_name, 'w', newline='') as f:
            json.dump(self.history, f)

    def load(self):
        with open(self.fine_name, newline='') as jsonfile:
            data = json.load(jsonfile)
        self.history = data
        return self.history


class MongoStorage:
    def __init__(self, db):
        self.db = db

    def save(self, data):
        user_id, api_key = list(data.items())[0]
        self.db['api_key'].update_one({
            'user_id': user_id
        }, {
            '$set': {
                'user_id': user_id,
                'api_key': api_key,
                'created_at': datetime.datetime.utcnow()
            }
        }, upsert=True)

    def GetUserAPIKey(self, id):
        res = self.db['api_key'].find_one({'user_id':id})
        if res:
            return res['api_key']
        else:
            return "Error"
        
    def IsInDatabase(self, id):
        res = self.db['api_key'].find_one({'user_id':id})
        if res:
            return True
        else:
            return False
    def GetMember(self, data):
        res = self.db['api_key'].find_one({'user_id':id})
        if res:
            return res['is_member']
        else:
            return False

    def SetMember(self, data):
        user_id = data
        self.db['api_key'].update_one({
            'user_id': user_id
        }, {
            '$set': {
                'is_member': True,
            }
        }, upsert=True)       
        
    def DeleteMember(self, data):
        user_id = data
        self.db['api_key'].update_one({
            'user_id': user_id
        }, {
            '$set': {
                'is_member': False,
            }
        }, upsert=True)

    def load(self):
        data = list(self.db['api_key'].find())
        res = {}
        for i in range(len(data)):
            res[data[i]['user_id']] = data[i]['api_key']
        return res


class Storage:
    def __init__(self, storage):
        self.storage = storage

    def save(self, data):
        self.storage.save(data)

    def load(self):
        return self.storage.load()
    
    def GetUserAPIKey(self, id):
        return self.storage.GetUserAPIKey(id)
        
    def IsInDatabase(self, id):
        return self.storage.IsInDatabase(id)
    
    def GetMember(self, data):
        return self.storage.GetMember(data)

    def SetMember(self, data):
        return self.storage.SetMember(data)
        
    def DeleteMember(self, data):
        return self.storage.DeleteMember(data)
