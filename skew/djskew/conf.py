from skew.bin.config import BaseConfiguration
from skew.djskew import config, queue, result_store


Configuration = type('Configuration', (BaseConfiguration,), config)
