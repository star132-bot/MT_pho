#!/usr/bin/env python3
"""Focused boundary checks for Header Identity signed-avatar refresh."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server

USER_ID = "81000000-0000-4000-8000-000000000001"
OTHER_USER_ID = "81000000-0000-4000-8000-000000000002"
UPLOAD_ID = "86000000-0000-4000-8000-000000000001"
AVATAR_KEY = f"{USER_ID}/{UPLOAD_ID}/avatar.jpg"


class HeaderHarness:
    signed_profile_avatar_coordinates = server.MTRequestHandler.signed_profile_avatar_coordinates
    sign_profile_avatar_asset = server.MTRequestHandler.sign_profile_avatar_asset
    refresh_signed_profile_avatar = server.MTRequestHandler.refresh_signed_profile_avatar
    absolute_storage_url = server.MTRequestHandler.absolute_storage_url

    @staticmethod
    def current_access_token(_user: dict) -> str:
        return "fixture-access-token"


def main() -> None:
    original_url = server.SUPABASE_URL
    original_request = server.supabase_storage_request
    calls: list[tuple[str, str, dict]] = []

    try:
        server.SUPABASE_URL = "https://project.example"

        def signed_response(path: str, access_token: str, payload: dict):
            calls.append((path, access_token, payload))
            return HTTPStatus.OK, {
                "signedURL": f"/object/sign/profile-avatars/{AVATAR_KEY}?token=fresh",
            }

        server.supabase_storage_request = signed_response
        harness = HeaderHarness()
        expired_url = (
            "https://project.example/storage/v1/object/sign/"
            f"profile-avatars/{AVATAR_KEY}?token=expired"
        )
        profile = {"display_name": "Header Member", "avatar_url": expired_url}
        refreshed = harness.refresh_signed_profile_avatar({"id": USER_ID}, profile)

        assert refreshed is not profile
        assert refreshed["avatar_url"].endswith("?token=fresh")
        assert calls == [
            (
                f"object/sign/profile-avatars/{AVATAR_KEY}",
                "fixture-access-token",
                {"expiresIn": server.HEADER_AVATAR_SIGNED_URL_TTL},
            )
        ]

        calls.clear()
        assert harness.sign_profile_avatar_asset({"id": USER_ID}, AVATAR_KEY).endswith("?token=fresh")
        assert calls == [
            (
                f"object/sign/profile-avatars/{AVATAR_KEY}",
                "fixture-access-token",
                {"expiresIn": server.PROFILE_AVATAR_SIGNED_URL_TTL},
            )
        ]

        def mismatched_response(path: str, access_token: str, payload: dict):
            return HTTPStatus.OK, {
                "signedURL": (
                    "/object/sign/profile-avatars/"
                    f"{OTHER_USER_ID}/{UPLOAD_ID}/avatar.jpg?token=fresh"
                ),
            }

        server.supabase_storage_request = mismatched_response
        assert harness.refresh_signed_profile_avatar({"id": USER_ID}, profile) is profile
        assert harness.sign_profile_avatar_asset({"id": USER_ID}, AVATAR_KEY) == ""

        calls.clear()
        external = {"display_name": "External", "avatar_url": "https://images.example/avatar.jpg"}
        assert harness.refresh_signed_profile_avatar({"id": USER_ID}, external) is external
        assert calls == []

        assert harness.signed_profile_avatar_coordinates(
            f"https://attacker.example/storage/v1/object/sign/profile-avatars/{AVATAR_KEY}",
            USER_ID,
        ) is None
        assert harness.signed_profile_avatar_coordinates(
            (
                "https://project.example/storage/v1/object/sign/profile-avatars/"
                f"{USER_ID}/{UPLOAD_ID}/../avatar.jpg"
            ),
            USER_ID,
        ) is None
        assert harness.signed_profile_avatar_coordinates(
            f"https://project.example/storage/v1/object/sign/profile-avatars/{USER_ID}/avatar.jpg",
            USER_ID,
        ) is None
        assert harness.signed_profile_avatar_coordinates(
            (
                "https://project.example/storage/v1/object/sign/profile-avatars/"
                f"{OTHER_USER_ID}/{UPLOAD_ID}/avatar.jpg"
            ),
            USER_ID,
        ) is None
    finally:
        server.SUPABASE_URL = original_url
        server.supabase_storage_request = original_request

    print("header_avatar_resign=yes")
    print("header_avatar_path_binding=yes")


if __name__ == "__main__":
    main()
