"""One-message anonymous vouch forwarding for ticket conversations."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

_PENDING_PATH = Path(__file__).with_name("vouch_pending.json")
_SETTINGS_PATH = Path(__file__).with_name("vouch_settings.json")
VOUCH_TIMEOUT_SECONDS = 15 * 60
_DISCORD_MENTION = re.compile(r"<(?:@!?|@&|#)\d+>")


@dataclass(frozen=True)
class PendingVouch:
    guild_id: int
    destination_channel_id: int
    expires_at: float


class VouchManager:
    """Keep at most one pending vouch per ticket channel, across restarts."""

    def __init__(self, path: Path = _PENDING_PATH) -> None:
        self._path = path
        self._settings_path = path.with_name(_SETTINGS_PATH.name)
        self._pending: dict[int, PendingVouch] = self._read_pending()
        self._destination_channels = self._read_destination_channels()
        self._remove_expired()

    def destination_channel_id(self, guild_id: int) -> int | None:
        return self._destination_channels.get(guild_id)

    def set_destination_channel(self, guild_id: int, channel_id: int) -> None:
        self._destination_channels[guild_id] = channel_id
        content = json.dumps(
            {
                str(saved_guild_id): saved_channel_id
                for saved_guild_id, saved_channel_id
                in self._destination_channels.items()
            },
            indent=2,
        ) + "\n"
        temporary_path = self._settings_path.with_suffix(".tmp")
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(self._settings_path)

    def get(self, ticket_channel_id: int) -> PendingVouch | None:
        pending = self._pending.get(ticket_channel_id)
        if pending is not None and pending.expires_at <= time.time():
            self.clear(ticket_channel_id)
            return None
        return pending

    def arm(
        self,
        ticket_channel_id: int,
        guild_id: int,
        destination_channel_id: int,
    ) -> bool:
        self._remove_expired()
        if ticket_channel_id in self._pending:
            return False

        self._pending[ticket_channel_id] = PendingVouch(
            guild_id=guild_id,
            destination_channel_id=destination_channel_id,
            expires_at=time.time() + VOUCH_TIMEOUT_SECONDS,
        )
        self._write_pending()
        return True

    def clear(self, ticket_channel_id: int) -> None:
        if self._pending.pop(ticket_channel_id, None) is not None:
            self._write_pending()

    def _remove_expired(self) -> None:
        now = time.time()
        expired = [
            channel_id
            for channel_id, pending in self._pending.items()
            if pending.expires_at <= now
        ]
        for channel_id in expired:
            del self._pending[channel_id]
        if expired:
            self._write_pending()

    def _read_pending(self) -> dict[int, PendingVouch]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Impossible de lire le fichier {self._path.name}."
            ) from error

        if not isinstance(raw, dict):
            raise RuntimeError(
                f"Le contenu de {self._path.name} doit être un objet JSON."
            )

        pending_vouches: dict[int, PendingVouch] = {}
        for channel_id, value in raw.items():
            if (
                not channel_id.isdecimal()
                or not isinstance(value, dict)
                or not all(
                    isinstance(value.get(key), int)
                    and not isinstance(value.get(key), bool)
                    and value[key] > 0
                    for key in ("guild_id", "destination_channel_id")
                )
                or not isinstance(value.get("expires_at"), (int, float))
            ):
                raise RuntimeError(
                    f"Une entrée est invalide dans {self._path.name}."
                )

            pending_vouches[int(channel_id)] = PendingVouch(
                guild_id=value["guild_id"],
                destination_channel_id=value["destination_channel_id"],
                expires_at=float(value["expires_at"]),
            )
        return pending_vouches

    def _read_destination_channels(self) -> dict[int, int]:
        try:
            raw = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Impossible de lire le fichier {self._settings_path.name}."
            ) from error

        if not isinstance(raw, dict) or any(
            not guild_id.isdecimal()
            or isinstance(channel_id, bool)
            or not isinstance(channel_id, int)
            or channel_id <= 0
            for guild_id, channel_id in raw.items()
        ):
            raise RuntimeError(
                f"Le contenu de {self._settings_path.name} est invalide."
            )
        return {int(guild_id): channel_id for guild_id, channel_id in raw.items()}

    def _write_pending(self) -> None:
        content = json.dumps(
            {
                str(channel_id): {
                    "guild_id": pending.guild_id,
                    "destination_channel_id": pending.destination_channel_id,
                    "expires_at": pending.expires_at,
                }
                for channel_id, pending in self._pending.items()
            },
            indent=2,
        ) + "\n"
        temporary_path = self._path.with_suffix(".tmp")
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(self._path)


def anonymize_vouch(content: str) -> str:
    """Remove Discord user, role, and channel mention markup."""
    return _DISCORD_MENTION.sub("[mention retirée]", content).strip()
