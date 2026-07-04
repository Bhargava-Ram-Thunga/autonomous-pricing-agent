"""Live-configurable default route. Persists to Postgres."""
import os

source = os.environ.get("DEFAULT_SOURCE", "BANGALORE")
destination = os.environ.get("DEFAULT_DEST", "TIRUPATI")


def load_from_db():
    global source, destination
    try:
        from state_store import kv_get
        s = kv_get("__global__", "default_source")
        d = kv_get("__global__", "default_destination")
        if s:
            source = s.upper().strip()
        if d:
            destination = d.upper().strip()
    except Exception:
        pass


def set_route(src: str, dst: str):
    global source, destination
    source = src.upper().strip()
    destination = dst.upper().strip()
    try:
        from state_store import kv_set
        kv_set("__global__", "default_source", source)
        kv_set("__global__", "default_destination", destination)
    except Exception as e:
        print(f"[route_config persist fail] {e}")
    return f"route set: {source} → {destination}"


def get_route() -> tuple[str, str]:
    return source, destination
