"""Source-derived interleavings of MainWindow's old hover pump, not a live UI test.

The original UI and worker share wantedPoint/wantedIds; there is no lock between
the listed steps. A fake transport records the calls that those steps would send.
"""
import json


def reproduce():
    evidence = []
    point, ids, running = (10, 20), "A", True
    transport = []
    target = point  # worker: var target = _wantedPoint
    point = (30, 40)  # UI: newer hover arrives while pumping is true
    point = None  # worker: _wantedPoint = null
    transport.append((ids, target))
    evidence.append({"case": "newest point cleared", "sent": transport,
                     "latest_requested": [30, 40], "pending": point})
    assert transport[-1][1] != (30, 40) and point is None

    point = None
    target = point  # worker decides to break because target is null
    point = (50, 60)  # UI sets wantedPoint; sees pumping=true, starts no worker
    running = False  # worker finally
    evidence.append({"case": "empty-worker exit strands a move",
                     "pending": point, "running": running})
    assert point is not None and not running

    point, ids, api = (70, 80), "A", "old connection"
    target = point  # worker snapshots only coordinates
    point, ids, api = (90, 100), "B", "new connection"  # selection/reconnect
    transport = [(api, ids, target)]  # worker reads the new client and ids
    evidence.append({"case": "coordinates mixed with another scope", "sent": transport})
    assert transport[0] == ("new connection", "B", (70, 80))

    queued_control = "cancelled by Stop"
    current_control = "fresh after Resume"
    worker_control = current_control  # read only when Task.Run starts
    evidence.append({"case": "worker captures replacement control lifetime",
                     "queued_control": queued_control, "worker_control": worker_control})
    assert worker_control != queued_control
    return {"scope": "deterministic source model; no UI, service or hardware", "cases": evidence}


if __name__ == "__main__":
    print(json.dumps(reproduce(), indent=2))
