"""One-message anonymous vouch forwarding for ticket conversations."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path

import discord
from discord.ext import commands

from config import VOUCH_PROMPT

_PENDING_PATH = Path(__file__).with_name("vouch_pending.json")
_SETTINGS_PATH = Path(__file__).with_name("vouch_settings.json")
VOUCH_TIMEOUT_SECONDS = 15 * 60
_DISCORD_MENTION = re.compile(r"<(?:@!?|@&|#)\d+>")


@dataclass(frozen=True)
class PendingVouch:
    guild_id: int
    destination_channel_id: int
    expires_at: float
    rating: int | None = None
    reviewer_user_id: int | None = None
    anonymous: bool | None = None

class VouchManager:
    """Keep one pending, rated vouch per ticket channel across restarts."""

    def __init__(self, path: Path = _PENDING_PATH) -> None:
        self._path = path
        self._settings_path = path.with_name(_SETTINGS_PATH.name)
        self._pending: dict[int, PendingVouch] = self._read_pending()
        self._destination_channels = self._read_destination_channels()
        self._publishing: set[int] = set()
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

    def record_rating(
        self,
        ticket_channel_id: int,
        reviewer_user_id: int,
        rating: int,
    ) -> bool:
        pending = self.get(ticket_channel_id)
        if pending is None or not 1 <= rating <= 5:
            return False
        if (
            pending.reviewer_user_id is not None
            and pending.reviewer_user_id != reviewer_user_id
        ):
            return False

        self._pending[ticket_channel_id] = replace(
            pending,
            rating=rating,
            reviewer_user_id=reviewer_user_id,
        )
        self._write_pending()
        return True

    def record_anonymity(
        self,
        ticket_channel_id: int,
        reviewer_user_id: int,
        anonymous: bool,
    ) -> bool:
        pending = self.get(ticket_channel_id)

        if pending is None or not isinstance(anonymous, bool):
            return False

        if (
            pending.reviewer_user_id is not None
            and pending.reviewer_user_id != reviewer_user_id
        ):
            return False

        self._pending[ticket_channel_id] = replace(
            pending,
            reviewer_user_id=reviewer_user_id,
            anonymous=anonymous,
        )

        self._write_pending()
        return True

    def pending_items(self) -> list[tuple[int, PendingVouch]]:
        self._remove_expired()
        return list(self._pending.items())

    def begin_publish(self, ticket_channel_id: int) -> bool:
        if ticket_channel_id in self._publishing:
            return False
        pending = self.get(ticket_channel_id)
        if pending is None or pending.rating is None:
            return False
        self._publishing.add(ticket_channel_id)
        return True

    def finish_publish(self, ticket_channel_id: int) -> None:
        self._publishing.discard(ticket_channel_id)

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
                or isinstance(value.get("expires_at"), bool)
                or not isinstance(value.get("expires_at"), (int, float))
            ):
                raise RuntimeError(
                    f"Une entrée est invalide dans {self._path.name}."
                )

            rating = value.get("rating")
            reviewer_user_id = value.get("reviewer_user_id")
            anonymous = value.get("anonymous")
            if (
                (rating is None) != (reviewer_user_id is None)
                or (
                    rating is not None
                    and (
                        isinstance(rating, bool)
                        or not isinstance(rating, int)
                        or not 1 <= rating <= 5
                    )
                )
                or (
                    reviewer_user_id is not None
                    and (
                        isinstance(reviewer_user_id, bool)
                        or not isinstance(reviewer_user_id, int)
                        or reviewer_user_id <= 0
                    )
                )
                 or (anonymous is not None and not isinstance(anonymous, bool))
            ):
                raise RuntimeError(
                    f"La note enregistrée est invalide dans {self._path.name}."
                )

            pending_vouches[int(channel_id)] = PendingVouch(
                guild_id=value["guild_id"],
                destination_channel_id=value["destination_channel_id"],
                expires_at=float(value["expires_at"]),
                rating=rating,
                reviewer_user_id=reviewer_user_id,
                anonymous=anonymous,
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
                    "rating": pending.rating,
                    "reviewer_user_id": pending.reviewer_user_id,
                    "anonymous": pending.anonymous,
                }
                for channel_id, pending in self._pending.items()
            },
            indent=2,
        ) + "\n"
        temporary_path = self._path.with_suffix(".tmp")
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(self._path)


class VouchRatingButton(discord.ui.Button):
    def __init__(
        self,
        manager: VouchManager,
        ticket_channel_id: int,
        rating: int,
    ) -> None:
        super().__init__(
            label=f"{rating} ⭐",
            style=discord.ButtonStyle.secondary,
            custom_id=f"vch-rate:{ticket_channel_id}:{rating}",
        )
        self.manager = manager
        self.ticket_channel_id = ticket_channel_id
        self.rating = rating

    async def callback(self, interaction: discord.Interaction) -> None:
        pending = self.manager.get(self.ticket_channel_id)
        if (
            pending is None
            or interaction.guild_id != pending.guild_id
            or interaction.channel_id != self.ticket_channel_id
        ):
            await interaction.response.send_message(
                "Cette demande de vouch a expiré. Le staff peut relancer `!vch`.",
                ephemeral=True,
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Cette note doit être donnée depuis le serveur.",
                ephemeral=True,
            )
            return
        if member.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "La note est réservée au client du ticket.",
                ephemeral=True,
            )
            return
        if not self.manager.record_rating(
            self.ticket_channel_id,
            member.id,
            self.rating,
        ):
            await interaction.response.send_message(
                "Un autre membre a déjà commencé ce vouch.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Note enregistrée : {'⭐' * self.rating} ({self.rating}/5). "
            f"Copie exactement `{VOUCH_PROMPT}` du message au-dessus et "
            "renvoie-le dans ce ticket. Ton nom et ta photo seront publics; "
            "le ticket sera supprimé après la publication.\n\n"
            f"Rating saved: {'⭐' * self.rating} ({self.rating}/5). Copy "
            f"`{VOUCH_PROMPT}` from the message above and send it in this "
            "ticket. Your name and photo will be public; the ticket will be "
            "deleted after posting.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )



class VouchRatingView(discord.ui.View):
    def __init__(self, manager: VouchManager, ticket_channel_id: int) -> None:
        super().__init__(timeout=None)
        for rating in range(1, 6):
            self.add_item(VouchRatingButton(manager, ticket_channel_id, rating))

class VouchPrivacyButton(discord.ui.Button):
    def __init__(
        self,
        manager: VouchManager,
        ticket_channel_id: int,
        anonymous: bool,
    ) -> None:
        super().__init__(
            label="Anonymous" if anonymous else "Public",
            emoji="🕶️" if anonymous else "👤",
            style=discord.ButtonStyle.secondary if anonymous else discord.ButtonStyle.primary,
            custom_id=f"vch-privacy:{ticket_channel_id}:{int(anonymous)}",
        )
        self.manager = manager
        self.ticket_channel_id = ticket_channel_id
        self.anonymous = anonymous

    async def callback(self, interaction: discord.Interaction) -> None:
        pending = self.manager.get(self.ticket_channel_id)

        if (
            pending is None
            or interaction.guild_id != pending.guild_id
            or interaction.channel_id != self.ticket_channel_id
        ):
            await interaction.response.send_message(
                "This vouch request has expired.",
                ephemeral=True,
            )
            return

        member = interaction.user

        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "You must be a server member.",
                ephemeral=True,
            )
            return

        if member.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "Only the customer can choose this option.",
                ephemeral=True,
            )
            return

        if not self.manager.record_anonymity(
            self.ticket_channel_id,
            member.id,
            self.anonymous,
        ):
            await interaction.response.send_message(
                "Another member has already started this vouch.",
                ephemeral=True,
            )
            return

        choice = "anonymous" if self.anonymous else "public"

        await interaction.response.edit_message(
            content=f"Your choice is saved: **{choice}**.\nNow choose your rating below!",
            view=VouchRatingView(self.manager, self.ticket_channel_id),
        )


class VouchPrivacyView(discord.ui.View):
    def __init__(self, manager: VouchManager, ticket_channel_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(VouchPrivacyButton(manager, ticket_channel_id, True))
        self.add_item(VouchPrivacyButton(manager, ticket_channel_id, False))


def register_saved_vouch_views(
    bot: commands.Bot,
    manager: VouchManager,
) -> None:
    for ticket_channel_id, pending in manager.pending_items():
        if pending.anonymous is None:
            bot.add_view(VouchPrivacyView(manager, ticket_channel_id))
        else:
            bot.add_view(VouchRatingView(manager, ticket_channel_id))



def sanitize_vouch_text(content: str) -> str:
    """Remove Discord mention markup from customer-provided text."""
    return _DISCORD_MENTION.sub("[mention retirée]", content).strip()
