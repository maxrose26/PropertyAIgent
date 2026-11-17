"""Non-secret build identity; no provider, database or council connection."""
import json
from .daily_intake_runtime import execution_binding

if __name__ == '__main__':
    print('TAMESIDE_BUILD_RECEIPT '+json.dumps(execution_binding(),sort_keys=True))
