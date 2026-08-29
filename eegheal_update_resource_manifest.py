from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent
IMAGE_DIR = ROOT / "eegheal_images"
AUDIO_DIR = ROOT / "eegheal_audio"
MANIFEST_PATH = ROOT / "eegheal_resource_manifest.json"
BASE_URL = "https://bci-kate.github.io/eegheal_resource"


def png_is_valid(path: Path) -> bool:
    with path.open("rb") as file:
        return file.read(8) == b"\x89PNG\r\n\x1a\n"


def ogg_duration_ms(path: Path) -> int:
    sample_rates: dict[int, int] = {}
    last_granules: dict[int, int] = {}

    with path.open("rb") as file:
        while True:
            header = file.read(27)
            if not header:
                break
            if len(header) != 27 or header[:4] != b"OggS":
                raise ValueError("不是有效的 OGG 文件")

            granule_position = struct.unpack_from("<Q", header, 6)[0]
            stream_serial = struct.unpack_from("<I", header, 14)[0]
            segment_count = header[26]
            segment_table = file.read(segment_count)
            if len(segment_table) != segment_count:
                raise ValueError("OGG segment table 不完整")

            payload_size = sum(segment_table)
            payload = file.read(payload_size)
            if len(payload) != payload_size:
                raise ValueError("OGG page 数据不完整")

            if payload.startswith(b"\x01vorbis") and len(payload) >= 16:
                sample_rate = struct.unpack_from("<I", payload, 12)[0]
                if sample_rate > 0:
                    sample_rates[stream_serial] = sample_rate

            if granule_position != 0xFFFFFFFFFFFFFFFF:
                last_granules[stream_serial] = max(
                    granule_position,
                    last_granules.get(stream_serial, 0),
                )

    durations = [
        round(last_granules[serial] * 1000 / sample_rate)
        for serial, sample_rate in sample_rates.items()
        if last_granules.get(serial, 0) > 0
    ]
    if not durations:
        raise ValueError("无法读取 OGG Vorbis 时长")
    return max(1, max(durations))


def public_url(folder: str, filename: str) -> str:
    return f"{BASE_URL}/{folder}/{quote(filename)}"


def scan_images() -> tuple[list[dict], list[str]]:
    resources = []
    skipped = []
    for path in sorted(IMAGE_DIR.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.lower() != ".png":
            skipped.append(str(path.name))
            continue
        if not png_is_valid(path):
            raise ValueError(f"无效 PNG：{path.name}")
        url = public_url(IMAGE_DIR.name, path.name)
        resources.append(
            {
                "resource_id": path.stem,
                "name": path.name,
                "url": url,
                "thumbnail_url": url,
                "format": "png",
            }
        )
    return resources, skipped


def scan_audio() -> tuple[list[dict], list[str]]:
    resources = []
    skipped = []
    for path in sorted(AUDIO_DIR.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.lower() != ".ogg":
            skipped.append(str(path.name))
            continue
        resources.append(
            {
                "resource_id": path.stem,
                "name": path.name,
                "url": public_url(AUDIO_DIR.name, path.name),
                "duration_ms": ogg_duration_ms(path),
                "format": "ogg",
            }
        )
    return resources, skipped


def validate_unique_ids(images: list[dict], audio: list[dict]) -> None:
    seen = set()
    for item in images + audio:
        resource_id = item["resource_id"]
        if resource_id in seen:
            raise ValueError(f"resource_id 重复：{resource_id}")
        seen.add(resource_id)


def main() -> None:
    if not IMAGE_DIR.is_dir():
        raise FileNotFoundError(f"图片目录不存在：{IMAGE_DIR}")
    if not AUDIO_DIR.is_dir():
        raise FileNotFoundError(f"音频目录不存在：{AUDIO_DIR}")

    images, skipped_images = scan_images()
    audio, skipped_audio = scan_audio()
    validate_unique_ids(images, audio)

    manifest = {"version": 1, "images": images, "audio": audio}
    temporary_path = MANIFEST_PATH.with_suffix(MANIFEST_PATH.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, MANIFEST_PATH)

    print(f"清单已更新：{MANIFEST_PATH}")
    print(f"图片：{len(images)} 个；音频：{len(audio)} 个")
    if skipped_images:
        print("图片目录跳过：" + ", ".join(skipped_images))
    if skipped_audio:
        print("音频目录跳过：" + ", ".join(skipped_audio))


if __name__ == "__main__":
    main()
