import os
import sys
import types
import tempfile

# Provide a fake Redis so the app imports without a server.
class FakeRedis:
    def __init__(self,*a,**k): pass
    @classmethod
    def from_url(cls,*a,**k): return cls()
    def rpush(self,k,v): pass
    def incr(self,k): return 1
    def expire(self,*a): pass
    def ping(self): return True

_redis=types.ModuleType('redis'); _redis.Redis=FakeRedis; sys.modules.setdefault('redis',_redis)

os.environ.setdefault('DATABASE_URL','sqlite:///'+tempfile.NamedTemporaryFile(suffix='.db',delete=False).name)
os.environ.setdefault('JWT_SECRET','test-secret')
os.environ.setdefault('REDIS_URL','redis://localhost:6379/0')
