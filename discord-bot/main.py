"""Discord bot for PayPal, Litecoin, and member verification."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import discord
from discord.ext import commands

from config import (
    LITECOIN_ADDRESS_SHIN,
    LITECOIN_ADDRESS_YASKO,
    PAYPAL_LINK,
    VOUCH_PROMPT,
)
from verification import (
    VerificationView,
    register_saved_verification_views,
    save_verification_role,
)
from vouches import (
    VouchManager,
    VouchPrivacyView,
    VouchRatingView,
    register_saved_vouch_views,
    sanitize_vouch_text,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("payment-bot")
vouch_manager = VouchManager()

intents = discord.Intents.default()
intents.message_content = True

class PaymentBot(commands.Bot):
    async def setup_hook(self) -> None:
        await super().setup_hook()
        register_saved_verification_views(self)
        register_saved_vouch_views(self, vouch_manager)


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
    """Send Shin's configured Litecoin address."""
    await _send_litecoin_address(ctx, "Shin Addy", LITECOIN_ADDRESS_SHIN)


@bot.command(name="ltcy")
async def litecoin_yasko(ctx: commands.Context[commands.Bot]) -> None:
    """Send Yasko's configured Litecoin address."""
    await _send_litecoin_address(ctx, "Yasko Addy", LITECOIN_ADDRESS_YASKO)


@bot.command(name="vchsetup")
@commands.guild_only()
@commands.has_guild_permissions(administrator=True)
async def vouch_setup(
    ctx: commands.Context[commands.Bot],
    channel: discord.TextChannel | None = None,
) -> None:
    """Configure or display the destination channel for customer vouches."""
    guild = ctx.guild
    if guild is None:
        await ctx.send("Cette commande doit être utilisée dans un serveur.")
        return

    bot_member = guild.me
    if bot_member is None:
        await ctx.send("Je ne peux pas vérifier mes permissions sur ce serveur.")
        return

    if channel is None:
        saved_channel_id = vouch_manager.destination_channel_id(guild.id)
        saved_channel = (
            guild.get_channel(saved_channel_id) if saved_channel_id is not None else None
        )
        if isinstance(saved_channel, discord.TextChannel):
            await ctx.send(f"Les vouches seront publiés dans {saved_channel.mention}.")
        else:
            await ctx.send("Aucun salon configuré. Utilise `!vchsetup #vouches`.")
        return

    permissions = channel.permissions_for(bot_member)
    if (
        not permissions.view_channel
        or not permissions.send_messages
        or not permissions.embed_links
    ):
        await ctx.send(
            "Le bot doit pouvoir voir ce salon, y envoyer des messages "
            "et intégrer des liens."
        )
        return

    vouch_manager.set_destination_channel(guild.id, channel.id)
    await ctx.send(f"Salon des vouches configuré : {channel.mention}.")


@bot.command(name="vch")
@commands.guild_only()
@commands.has_guild_permissions(manage_messages=True)
async def vouch(ctx: commands.Context[commands.Bot]) -> None:
    """Collect a rated vouch, publish it with attribution, and delete the ticket."""
    guild = ctx.guild
    if guild is None:
        await ctx.send("Cette commande doit être utilisée dans un serveur.")
        return

    destination_channel_id = vouch_manager.destination_channel_id(guild.id)
    destination = (
        guild.get_channel(destination_channel_id)
        if destination_channel_id is not None
        else None
    )
    if not isinstance(destination, discord.TextChannel):
        await ctx.send(
            "Le salon de vouches n'est pas configuré. "
            "Un administrateur doit lancer `!vchsetup #vouches`."
        )
        return
    if destination.id == ctx.channel.id:
        await ctx.send(
            "Le salon de publication ne peut pas être le ticket qui sera supprimé."
        )
        return

    pending = vouch_manager.get(ctx.channel.id)
    if pending is not None:
        if pending.reviewer_user_id is not None:
            await ctx.send(
                "Un client a déjà commencé son vouch dans ce ticket. "
                "Attends son avis ou l'expiration de la demande."
            )
            return
        # Refresh an unanswered request, including requests created by the old flow.
        vouch_manager.clear(ctx.channel.id)

    bot_member = guild.me
    ticket_permissions = (
        ctx.channel.permissions_for(bot_member) if bot_member else None
    )
    destination_permissions = (
        destination.permissions_for(bot_member) if bot_member else None
    )
    can_delete_ticket = False
    if ticket_permissions is not None:
        if isinstance(ctx.channel, discord.Thread):
            can_delete_ticket = (
                ticket_permissions.manage_threads
                or ticket_permissions.manage_channels
            )
        else:
            can_delete_ticket = ticket_permissions.manage_channels
    if (
        ticket_permissions is None
        or not ticket_permissions.view_channel
        or not ticket_permissions.send_messages
        or not ticket_permissions.embed_links
        or not can_delete_ticket
        or destination_permissions is None
        or not destination_permissions.view_channel
        or not destination_permissions.send_messages
        or not destination_permissions.embed_links
    ):
        await ctx.send(
            "Dans le ticket, le bot doit pouvoir envoyer des messages et intégrer "
            "des liens, ainsi que gérer les salons (ou les fils). Il doit aussi "
            "pouvoir envoyer des embeds dans le salon des vouches."
        )
        return

    if not vouch_manager.arm(ctx.channel.id, guild.id, destination.id):
        await ctx.send("Un vouch est déjà en attente dans ce ticket.")
        return
    try:
        await ctx.send(
            VOUCH_PROMPT,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        instructions = discord.Embed(
            title="Laisse ton avis / Leave a review",
            description=(
                "**Français**\n"
                "Choisis d'abord une note de **1 à 5 étoiles**. Copie ensuite "
                f"exactement `{VOUCH_PROMPT}` dans le message juste au-dessus et "
                "renvoie-le dans ce ticket comme nouveau message.\n\n"
                f"Ton **nom d'utilisateur Discord** et ta **photo de profil** "
                f"seront publiés avec ta note dans {destination.mention}. "
                "Après publication, ce ticket sera supprimé automatiquement. "
                "Sans note, il ne sera pas supprimé. N'inclus pas d'informations "
                "personnelles."
                "\n\n"
                "**English**\n"
                "First choose a rating from **1 to 5 stars**. Then copy exactly "
                f"`{VOUCH_PROMPT}` from the message above and send it in this "
                "ticket as a new message.\n\n"
                f"Your **Discord username** and **profile picture** will be "
                f"published with your rating in {destination.mention}. After "
                "posting, this ticket will be deleted automatically. Without a "
                "rating, it will not be deleted. Do not include personal "
                "information."
            ),
            color=discord.Color(0x5865F2),
        )
        await ctx.send(
            embed=instructions,
            view=VouchRatingView(vouch_manager, ctx.channel.id),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException:
        vouch_manager.clear(ctx.channel.id)
        raise


@bot.listen("on_message")
async def forward_vouch(message: discord.Message) -> None:
    """Forward a rated text response with the customer's Discord identity."""
    if message.author.bot or message.guild is None:
        return
    if not isinstance(message.author, discord.Member):
        return

    pending = vouch_manager.get(message.channel.id)
    if pending is None or pending.guild_id != message.guild.id:
        return

    # Staff messages and bot commands must not be mistaken for a customer's vouch.
    if message.author.guild_permissions.manage_messages:
        return
    if message.content.startswith("!"):
        return

    if pending.rating is None or pending.reviewer_user_id != message.author.id:
        return

    if message.content.strip() != VOUCH_PROMPT.strip():
        await message.channel.send(
            f"Copie exactement `{VOUCH_PROMPT}` dans le message ci-dessus et "
            "renvoie-le ici. Le ticket ne sera supprimé qu'après l'envoi correct.\n\n"
            f"Copy exactly `{VOUCH_PROMPT}` from the message above and send it "
            "here. The ticket will only be deleted after the correct message."
        )
        return

    content = sanitize_vouch_text(message.content)
    if not content:
        if message.attachments:
            await message.channel.send(
                f"Copie exactement `{VOUCH_PROMPT}` et envoie-le dans le ticket."
            )
        return

    destination = message.guild.get_channel(pending.destination_channel_id)
    if not isinstance(destination, discord.TextChannel):
        vouch_manager.clear(message.channel.id)
        await message.channel.send(
            "Le salon configuré pour les vouches est introuvable. "
            "Un membre du staff peut relancer `!vch` après l'avoir recréé."
        )
        return

    embed = discord.Embed(
        title="Nouveau vouch",
        description=content[:4096],
        color=discord.Color(0x57F287),
    )
    embed.set_author(
        name=f"{message.author.display_name} (@{message.author.name})",
        icon_url=message.author.display_avatar.url,
    )
    embed.add_field(
        name="Note",
        value=f"{'⭐' * pending.rating} ({pending.rating}/5)",
        inline=False,
    )
    if not vouch_manager.begin_publish(message.channel.id):
        return
    try:
        await destination.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.Forbidden:
        vouch_manager.clear(message.channel.id)
        vouch_manager.finish_publish(message.channel.id)
        await message.channel.send(
            "Je n'ai pas la permission de publier dans le salon configuré. "
            "Vérifie ses permissions. Le ticket n'a pas été supprimé."
        )
        return
    except discord.HTTPException:
        logger.exception("Impossible de publier le vouch dans #vouches")
        vouch_manager.clear(message.channel.id)
        vouch_manager.finish_publish(message.channel.id)
        await message.channel.send(
            "Je n'ai pas pu publier le vouch. Le ticket n'a pas été supprimé."
        )
        return

    vouch_manager.clear(message.channel.id)
    vouch_manager.finish_publish(message.channel.id)
    try:
        await message.channel.send(
            "Ton vouch a été publié; ce ticket va maintenant être supprimé."
        )
    except discord.HTTPException:
        logger.info("Impossible d'envoyer la confirmation avant suppression du ticket")

    try:
        await message.channel.delete(
            reason=f"Vouch publié avec une note de {pending.rating}/5"
        )
    except discord.Forbidden:
        logger.exception("Permission refusée pour supprimer le ticket après le vouch")
        try:
            await message.channel.send(
                "Le vouch est publié, mais je n'ai pas pu supprimer ce ticket. "
                "Vérifie la permission de gestion des salons ou des fils."
            )
        except discord.HTTPException:
            pass
    except discord.HTTPException:
        logger.exception("Impossible de supprimer le ticket après le vouch")
        try:
            await message.channel.send(
                "Le vouch est publié, mais le ticket n'a pas pu être supprimé."
            )
        except discord.HTTPException:
            pass


async def _send_litecoin_address(
    ctx: commands.Context[commands.Bot],
    owner: str,
    configured_address: str,
) -> None:
    address = configured_address.strip()
    if not address:
        await ctx.send(
            f"L'adresse Litecoin de {owner} n'est pas encore configurée. "
            "Ajoute-la dans discord-bot/config.py."
        )
        return

    embed = discord.Embed(
        title=f"Adresse Litecoin — {owner}",
        description="Envoie ton paiement à l’adresse de réception ci-dessous.",
        color=discord.Color(0x345D9D),
    )
    embed.add_field(
        name=owner,
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
        if ctx.command is not None and ctx.command.name == "vch":
            await ctx.send(
                "La commande `!vch` est réservée au staff ayant "
                "la permission « Gérer les messages »."
            )
        elif ctx.command is not None and ctx.command.name == "vchsetup":
            await ctx.send("Seuls les administrateurs peuvent configurer le salon des vouches.")
        else:
            await ctx.send("Seuls les administrateurs peuvent publier le panneau.")
        return

    if isinstance(error, commands.MissingRequiredArgument):
        if ctx.command is not None and ctx.command.name == "verifysetup":
            await ctx.send("Utilisation : `!verifysetup @RôleVérifié`")
            return

    if isinstance(error, commands.BadArgument):
        if ctx.command is not None and ctx.command.name == "vchsetup":
            await ctx.send("Utilisation : `!vchsetup #vouches`")
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
