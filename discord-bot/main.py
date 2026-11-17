"""Discord bot with commands for PayPal and Litecoin payments."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import discord
from discord.ext import commands

from config import LITECOIN_ADDRESS, PAYPAL_LINK

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("payment-bot")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


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
