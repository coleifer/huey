from huey.bin.config import BaseConfiguration
from huey.djhuey import config, queue, result_store


Configuration = type('Configuration', (BaseConfiguration,), config)
