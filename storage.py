"""
storage.py — JSON-file storage backed by a Railway Volume.

Data lives at  /data/coupons.json  (the Volume is mounted at /data).
Structure:
{
  "folders": {
    "<folder_id>": {
      "id":         "abc123",
      "name":       "Nike June 2025",
      "created_at": "2025-06-01T10:00:00",
      "coupons": {
        "<coupon_id>": {
          "id":          "xyz789",
          "code":        "NIKE20",
          "description": "20% off everything",
          "created_at":  "2025-06-01T10:05:00"
        }
      }
    }
  }
}
"""

import json
import os
import uuid
import threading
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Railway Volume is mounted at /data by default (set in railway.toml)
DATA_DIR  = Path(os.environ.get("STORAGE_PATH", "/data"))
DATA_FILE = DATA_DIR / "coupons.json"

_lock = threading.Lock()   # thread-safe writes


# ── Internal helpers ─────────────────────────────────────────────────────────

def _load() -> dict:
    if not DATA_FILE.exists():
        return {"folders": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(DATA_FILE)   # atomic rename


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


def _uid() -> str:
    return uuid.uuid4().hex[:10]


# ── Public API ───────────────────────────────────────────────────────────────

def init():
    """Ensure the data directory and file exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        _save({"folders": {}})
    logger.info(f"Storage ready at {DATA_FILE}")


# Folders ────────────────────────────────────────────────────────────────────

def create_folder(name: str) -> str:
    with _lock:
        data = _load()
        fid  = _uid()
        data["folders"][fid] = {
            "id":         fid,
            "name":       name,
            "created_at": _now(),
            "coupons":    {},
        }
        _save(data)
    return fid


def get_folders() -> list:
    """Returns folders sorted newest-first with a coupon_count field."""
    data = _load()
    folders = []
    for f in data["folders"].values():
        folders.append({
            **f,
            "coupon_count": len(f["coupons"]),
        })
    folders.sort(key=lambda x: x["created_at"], reverse=True)
    return folders


def get_folder(folder_id: str) -> dict | None:
    data = _load()
    return data["folders"].get(folder_id)


def delete_folder(folder_id: str):
    with _lock:
        data = _load()
        data["folders"].pop(folder_id, None)
        _save(data)


# Coupons ────────────────────────────────────────────────────────────────────

def add_coupon(folder_id: str, code: str, description: str = "") -> str:
    with _lock:
        data = _load()
        folder = data["folders"].get(folder_id)
        if not folder:
            raise KeyError(f"Folder {folder_id} not found")
        cid = _uid()
        folder["coupons"][cid] = {
            "id":          cid,
            "code":        code,
            "description": description,
            "created_at":  _now(),
        }
        _save(data)
    return cid


def get_coupons(folder_id: str) -> list:
    """Returns coupons in a folder sorted newest-first."""
    data   = _load()
    folder = data["folders"].get(folder_id, {})
    coupons = list(folder.get("coupons", {}).values())
    coupons.sort(key=lambda x: x["created_at"], reverse=True)
    return coupons


def get_all_coupons() -> list:
    """All coupons across all folders, enriched with folder_name."""
    data    = _load()
    result  = []
    for folder in data["folders"].values():
        for c in folder["coupons"].values():
            result.append({**c, "folder_name": folder["name"], "folder_id": folder["id"]})
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return result


def get_coupon(coupon_id: str) -> dict | None:
    data = _load()
    for folder in data["folders"].values():
        if coupon_id in folder["coupons"]:
            return {**folder["coupons"][coupon_id], "folder_name": folder["name"]}
    return None


def delete_coupon(coupon_id: str):
    with _lock:
        data = _load()
        for folder in data["folders"].values():
            if coupon_id in folder["coupons"]:
                del folder["coupons"][coupon_id]
                _save(data)
                return
