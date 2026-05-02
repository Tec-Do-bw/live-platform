
import json
from core.apollo import APOLLO

KAFKA_HOSTS = APOLLO.get_value(key='kafka', default_val='')
