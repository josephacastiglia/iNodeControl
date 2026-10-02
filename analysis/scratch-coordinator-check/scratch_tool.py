"""Hardware-free receiver config check. No I/O, no device access."""

_FIELDS = {
    "receiver_name": str,
    "port": int,
    "device_id": str,
}


def validate_receiver_config(cfg):
    if not isinstance(cfg, dict) or set(cfg) != set(_FIELDS):
        return False
    if not all(type(cfg[key]) is expected for key, expected in _FIELDS.items()):
        return False
    return (
        1 <= cfg["port"] <= 65535
        and bool(cfg["receiver_name"].strip())
        and bool(cfg["device_id"].strip())
    )


if __name__ == "__main__":
    good = {"receiver_name": "rx", "port": 1, "device_id": "d"}
    assert validate_receiver_config(good) is True
    assert validate_receiver_config({**good, "port": 65535}) is True
    assert validate_receiver_config({**good, "port": 0}) is False
    assert validate_receiver_config({**good, "port": -1}) is False
    assert validate_receiver_config({**good, "port": 65536}) is False
    assert validate_receiver_config({**good, "receiver_name": ""}) is False
    assert validate_receiver_config({**good, "receiver_name": "   "}) is False
    assert validate_receiver_config({**good, "device_id": ""}) is False
    assert validate_receiver_config({**good, "device_id": "   "}) is False
    assert validate_receiver_config({**good, "port": True}) is False
    assert validate_receiver_config({**good, "port": "1"}) is False
    assert validate_receiver_config({}) is False
    assert validate_receiver_config(None) is False
    assert validate_receiver_config({**good, "extra": 1}) is False
    print("ok")
