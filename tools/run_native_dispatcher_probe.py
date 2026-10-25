#!/usr/bin/env python3
"""Check every v3 dispatcher kind refuses wrong-world input without mutation."""

import json
import struct

from admin_transport import AdminClient, AdminProtocolError
import admin_transport as transport
from native_bus_transport import BusBridge
from native_mutation_journal import normalize_position
from native_play_session import NativeSession
from run_environment_probe import require


class CapturedRequest(Exception):
    def __init__(self, payload):
        self.payload = payload


class RequestEncoder(AdminClient):
    """Use production codecs without connecting or sending a request."""

    def __init__(self):
        super().__init__(1, "not-used")

    def _require_connected(self):
        pass

    def _send_packet(self, packet_type, payload, deadline):
        require(packet_type == transport._ADMIN_COPILOT, "unexpected request packet type")
        raise CapturedRequest(payload)


def wrong_world_requests():
    encoder = RequestEncoder()
    world = "dispatcher-probe-wrong-world"
    operation = {"world_id": world, "operation_hi": 1, "operation_lo": 2}
    mutation = {**operation, "company_id": 0, "max_cost": 1,
                "expected_sequence": 0, "expected_head_hi": 0, "expected_head_lo": 0,
                "payload_hash_hi": 3, "payload_hash_lo": 4}
    calls = [
        ("copilot_build_single_rail", {**mutation, "tile": 8255, "rail_type": 0, "track": 0}),
        ("copilot_operation_status", operation),
        ("copilot_vehicle_events", {"world_id": world, "company_id": 0, "vehicle_id": 0}),
        ("copilot_tile_snapshot", {"world_id": world, "start_tile": 0, "count": 1}),
        ("copilot_industry_snapshot", {"world_id": world, "start_index": 0, "count": 1}),
        ("copilot_rail_catalog", {"world_id": world, "company_id": 0, "start_index": 0, "count": 1}),
        ("copilot_rail_assets", {"world_id": world, "company_id": 0,
                               "asset_kind": 0, "start_index": 0, "count": 1}),
        ("copilot_train_parts", {"world_id": world, "company_id": 0}),
        ("copilot_train_orders", {"world_id": world, "company_id": 0, "vehicle_id": 0}),
        ("copilot_industry_details", {"world_id": world, "start_index": 0}),
        ("copilot_build_infrastructure", {**mutation, "tile": 8255, "rail_type": 0,
                                          "orientation": 0, "infrastructure_kind": 1, "length": 2}),
        ("copilot_infrastructure_status", operation),
        ("copilot_build_train", {**mutation, "depot_tile": 8255, "engine_id": 0}),
        ("copilot_train_purchase_status", operation),
        ("copilot_configure_train", {**mutation, "tile": 8255, "action": 5,
                                     "vehicle_id": 0, "target_id": 0, "order_index": 0, "policy": 0}),
        ("copilot_train_configuration_status", operation),
        ("copilot_construction_quote", {"world_id": world, "company_id": 0, "tile": 8255,
                                        "rail_type": 0, "orientation": 0, "kind": 0, "length": 0}),
    ]
    requests = []
    for index, (method, fields) in enumerate(calls, start=1):
        try:
            getattr(encoder, method)(**fields, request_id=index)
        except CapturedRequest as captured:
            requests.append((method, captured.payload, 5))
        else:
            raise RuntimeError(f"{method} did not encode a request")
    body = {"action": "towns", "company_id": 0, "world_id": world, "start": 0, "count": 1}
    requests.append(("bus_wrong_world", struct.pack("<HBI", 3, 18, 18) +
                     json.dumps(body, separators=(",", ":")).encode() + b"\0", 5))
    return requests


def guard_requests():
    requests = wrong_world_requests()
    requests.append(("missing_company", struct.pack("<HBIB", 3, 0, 19, 254), 3))
    for index, version in enumerate((0, 4, 65535), start=20):
        requests.append((f"unsupported_version_{version}",
                         struct.pack("<HBIB", version, 0, index, 255), 1))
    for index, (version, kind) in enumerate(((1, 1), (2, 3), (3, 255)), start=23):
        requests.append((f"unsupported_kind_v{version}_{kind}",
                         struct.pack("<HBI", version, kind, index) + b"\0" * 128,
                         1 if version != 3 else 2))
    requests.append(("malformed_bus_json", struct.pack("<HBI", 3, 18, 26) + b"{\0", 7))
    return requests


def malformed_requests():
    return [
        ("short_header", b"\x03\x00"),
        ("missing_identity_company", struct.pack("<HBI", 3, 0, 27)),
        ("identity_trailing_bytes", struct.pack("<HBIBB", 3, 0, 28, 255, 0)),
        ("unterminated_bus_string", struct.pack("<HBI", 3, 18, 29) + b"{"),
    ]


def raw_exchange(admin, payload, timeout):
    deadline = admin._deadline(timeout)
    admin._send_packet(transport._ADMIN_COPILOT, payload, deadline)
    while True:
        packet_type, response = admin._read_frame(deadline)
        if packet_type == transport._SERVER_ERROR:
            admin._raise_server_error(response)
        if packet_type == transport._SERVER_GAMESCRIPT:
            admin._preserve_response(admin._decode_gamescript(
                response, "received", len(response) + transport._HEADER_SIZE))
        if packet_type == transport._SERVER_COPILOT:
            return response


def check_response(payload, response, status):
    _, kind, request_id = struct.unpack_from("<HBI", payload)
    expected = struct.pack("<HBIB", 3, kind, request_id, status)
    if response != expected:
        raise AdminProtocolError(
            f"dispatcher response bytes differ: expected {expected.hex()}, received {response.hex()}")


def finances(identity):
    return [{key: company[key] for key in ("id", "money", "loan")}
            for company in identity["companies"]]


def main():
    session = NativeSession(timeout=120)
    failure = None
    try:
        before = session.start_world("dispatcher")
        bridge = BusBridge(session.admin)
        quote = bridge.quote(before["world_id"], 7, road_bits=5)
        outcomes = []
        for name, payload, status in guard_requests():
            response = raw_exchange(session.admin, payload, session.remaining())
            check_response(payload, response, status)
            outcomes.append({"name": name, "request_hex": payload.hex(), "response_hex": response.hex()})
        malformed = []
        for name, payload in malformed_requests():
            try:
                raw_exchange(session.admin, payload, session.remaining())
            except transport.AdminServerError as exc:
                require(exc.code == 4, f"{name} did not return NETWORK_ERROR_ILLEGAL_PACKET: {exc}")
                malformed.append({"name": name, "request_hex": payload.hex(), "admin_error": exc.code})
            except EOFError:
                malformed.append({"name": name, "request_hex": payload.hex(), "connection_closed": True})
            else:
                raise RuntimeError(f"{name} was not rejected as an illegal packet")
            session.admin.close()
            session.connect()
        after = session.admin.copilot_identity(timeout=session.remaining())
        session.manifest["guard_observations"] = {
            "before": before, "after": after, "responses": outcomes, "malformed": malformed}
        session.write()
        require(normalize_position(before) == normalize_position(after), "guard requests changed history")
        require(finances(before) == finances(after), "guard requests changed finances")
        after_quote = BusBridge(session.admin).quote(after["world_id"], 7, road_bits=5)
        require(quote["retained_count"] == after_quote["retained_count"] == 0,
                "guard requests consumed retained history")
        session.check("all_dispatcher_kinds_wrong_world_and_exact_error_bytes", outcomes)
        session.check("malformed_payloads_refused_and_reconnect", malformed)
        session.check("guards_nonmutating", {"before": before, "after": after,
                                             "retained_count": after_quote["retained_count"]})
        session.save("dispatcher-guards-final")
    except Exception as exc:
        failure = exc
    return session.finish(failure)


if __name__ == "__main__":
    raise SystemExit(main())
