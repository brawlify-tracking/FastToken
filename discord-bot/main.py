"""Discord bot with commands for PayPal and Litecoin payments."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import discord
from discord.ext import commands

from config import LITECOIN_ADDRESS, PAYPAL_LINK
from verification import (
    VerificationView,
    register_saved_verification_views,
    save_verification_role,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("payment-bot")

intents = discord.Intents.default()
intents.message_content = True

class PaymentBot(commands.Bot):
    async def setup_hook(self) -> None:
        await super().setup_hook()
        register_saved_verification_views(self)


bot = PaymentBot(command_prefix="!", intents=intents, help_command=None)


def _valid_paypal_link(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


@bot.event
async def on_ready() -> None:
    logger.info("Bot connecté en tant que %s", bot.user)


@bot.command(name="ppl")
async def paypal(ctx: commands.Context[commands.Bot]) -> None:
    """Send the configured PayPal link."""
    link = PAYPAL_LINK.strip()
    if not link:
        await ctx.send(
            "Le lien PayPal n'est pas configuré. "
            "Ajoute-le dans discord-bot/config.py."
        )
        return

    if not _valid_paypal_link(link):
        await ctx.send(
            "Le lien PayPal doit être une URL HTTPS valide. "
            "Vérifie discord-bot/config.py."
        )
        return

    embed = discord.Embed(
        title="Paiement PayPal",
        description="Accède au paiement avec le bouton ci-dessous.",
        color=discord.Color(0x003087),
    )
    embed.set_footer(text="Lien de paiement PayPal")

    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="Ouvrir PayPal",
            style=discord.ButtonStyle.link,
            url=link,
        )
    )
    await ctx.send(
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.command(name="ltc")
async def litecoin(ctx: commands.Context[commands.Bot]) -> None:
    """Send the configured Litecoin address."""
    address = LITECOIN_ADDRESS.strip()
    if not address:
        await ctx.send(
            "L'adresse Litecoin n'est pas configurée. "
            "Ajoute-la dans discord-bot/config.py."
        )
        return

    embed = discord.Embed(
        title="Paiement en Litecoin",
        description="Envoie ton paiement à l’adresse de réception ci-dessous.",
        color=discord.Color(0x345D9D),
    )
    embed.add_field(
        name="Adresse Litecoin",
        value=f"```text\n{address}\n```",
        inline=False,
    )
    embed.set_footer(text="Vérifie l’adresse et le réseau avant l’envoi.")

    await ctx.send(
        embed=embed,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.command(name="verifysetup")
@commands.guild_only()
@commands.has_guild_permissions(administrator=True)
async def verify_setup(
    ctx: commands.Context[commands.Bot],
    role: discord.Role,
) -> None:
    """Post a verification panel that assigns the selected role."""
    guild = ctx.guild
    if guild is None:
        await ctx.send("Cette commande doit être utilisée dans un serveur.")
        return

    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        await ctx.send(
            "Le bot a besoin de la permission « Gérer les rôles » "
            "pour attribuer le rôle de vérification."
        )
        return

    if role.is_default() or role.managed:
        await ctx.send("Choisis un rôle de membre normal, pas un rôle géré.")
        return

    if role >= bot_member.top_role:
        await ctx.send(
            "Dans les paramètres du serveur, place le rôle du bot au-dessus "
            "du rôle de vérification, puis réessaie."
        )
        return

    save_verification_role(bot, role.id)

    embed = discord.Embed(
        title="Vérification du serveur",
        description=(
            "Clique sur le bouton ci-dessous pour vérifier ton compte et "
            f"obtenir le rôle **{role.name}**."
        ),
        color=discord.Color(0x3BA55D),
    )
    embed.set_footer(text="Cette étape donne accès aux salons réservés aux membres.")
    await ctx.send(
        embed=embed,
        view=VerificationView(role.id),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.event
async def on_command_error(
    ctx: commands.Context[commands.Bot],
    error: commands.CommandError,
) -> None:
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Seuls les administrateurs peuvent publier le panneau.")
        return

    if isinstance(error, commands.MissingRequiredArgument):
        if ctx.command is not None and ctx.command.name == "verifysetup":
            await ctx.send("Utilisation : `!verifysetup @RôleVérifié`")
            return

    if isinstance(error, commands.BadArgument):
        if ctx.command is not None and ctx.command.name == "verifysetup":
            await ctx.send("Mentionne le rôle à attribuer, par exemple `!verifysetup @Membre`.")
            return

    logger.error(
        "Erreur sur la commande %s",
        ctx.command,
        exc_info=(type(error), error, error.__traceback__),
    )


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit(
            "Erreur : le secret DISCORD_TOKEN est absent. "
            "Ajoute le token du bot dans Tools > Secrets, puis relance-le."
        )

    bot.run(token)


if __name__ == "__main__":
    main()
