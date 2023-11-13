# Python
import redis
from config import conf


class RedisUtil:
    def __init__(self):
        _host = conf().get("redis_host", "localhost")
        _port = conf().get("redis_port", "6379")
        _password = conf().get("redis_pwd", "")
        self.client = redis.StrictRedis(host=_host, port=_port, db=0, password=_password)

    def set_key(self, key, value):
        self.client.set(key, value)

    def get_key(self, key):
        return self.client.get(key)

    def delete_key(self, key):
        self.client.delete(key)

    def set_key_with_expiry(self, key, value, expiry_seconds):
        self.client.setex(key, expiry_seconds, value)

    def increment(self, key, amount=1):
        return self.client.incr(key, amount)

    def decrement(self, key, amount=1):
        return self.client.decr(key, amount)