from huey import RedisHuey

huey = RedisHuey('simple.test', blocking=True)
