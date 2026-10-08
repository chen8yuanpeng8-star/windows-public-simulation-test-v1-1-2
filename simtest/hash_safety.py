import copy
import hashlib
import json


def freeze_and_hash(payload):
    frozen = copy.deepcopy(payload)
    encoded = json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return frozen, hashlib.sha256(encoded).hexdigest()


def serialized_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

