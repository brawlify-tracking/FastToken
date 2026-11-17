"""Persistent button-based role verification for the Discord bot."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger("payment-bot.verification")
_ROLE_IDS_PATH = Path(__file__).with_name("verification_roles.json")
_saved_role_ids: set[int] = set()
_registered_role_ids: set[int] = set()


def _read_role_ids() -> set[int]:
    try:
        saved_ids = json.loads(_ROLE_IDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Impossible de lire le fichier de rôles de vérification "
            f"{_ROLE_IDS_PATH.name}."
        ) from error

    if not isinstance(saved_ids, list) or any(
        isinstance(role_id, bool)
        or not isinstance(role_id, int)
        or role_id <= 0
        for role_id in saved_ids
    ):
        raise RuntimeError(
            f"Le contenu de {_ROLE_IDS_PATH.name} doit être une liste d'identifiants "
            "de rôles Discord."
        )

    return set(saved_ids)


def _write_role_ids(role_ids: set[int]) -> None:
    temporary_path = _ROLE_IDS_PATH.with_suffix(".tmp")
    content = json.dumps(sorted(role_ids), indent=2) + "\n"
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(_ROLE_IDS_PATH)


class VerificationButton(discord.ui.Button):
    def __init__(self, role_id: int) -> None:
        super().__init__(
            label="Vérifier mon compte",
            style=discord.ButtonStyle.success,
            custom_id=f"verify-member:{role_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Cette vérification doit être faite depuis le serveur.",
                ephemeral=True,
            )
            return

        role = guild.get_role(self.role_id)
        if role is None:
            await interaction.response.send_message(
                "Le rôle de vérification n'existe plus. Contacte un administrateur.",
                ephemeral=True,
            )
            return

        if role in member.roles:
            await interaction.response.send_message(
                "Ton compte est déjà vérifié.",
                ephemeral=True,
            )
            return

        try:
            await member.add_roles(role, reason="Vérification par bouton")
        except discord.Forbidden:
            logger.warning(
                "Impossible d'attribuer le rôle de vérification %s dans le serveur %s",
                self.role_id,
                guild.id,
            )
            await interaction.response.send_message(
                "Le bot ne peut pas attribuer ce rôle. Vérifie sa permission "
                "« Gérer les rôles » et place son rôle au-dessus du rôle vérifié.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Vérification terminée. Tu as maintenant accès au serveur.",
            ephemeral=True,
        )


class VerificationView(discord.ui.View):
    def __init__(self, role_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(VerificationButton(role_id))


def _register_role_view(bot: commands.Bot, role_id: int) -> None:
    if role_id in _registered_role_ids:
        return

    bot.add_view(VerificationView(role_id))
    _registered_role_ids.add(role_id)


def register_saved_verification_views(bot: commands.Bot) -> None:
    _saved_role_ids.update(_read_role_ids())
    for role_id in _saved_role_ids:
        _register_role_view(bot, role_id)


def save_verification_role(bot: commands.Bot, role_id: int) -> None:
    updated_role_ids = _saved_role_ids | {role_id}
    if role_id not in _saved_role_ids:
        _write_role_ids(updated_role_ids)
        _saved_role_ids.update(updated_role_ids)

    _register_role_view(bot, role_id)
