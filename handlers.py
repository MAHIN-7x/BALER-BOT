import asyncio
import logging

import database as db
from api_client import HeroSMSClient
import keyboards as kb
from states import BotStates

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

router = Router()

ADMIN_ID    = 7266067201
COLOMBIA_ID = 33
TG_SERVICE  = "tg"
MAX_PRICE   = 0.135

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
async def is_allowed(user_id: int) -> bool:
    """Return True if the user is allowed to use the bot."""
    if user_id == ADMIN_ID:
        return True
    user = await db.get_user(user_id)
    if user and user["is_banned"]:
        return False
    maintenance = await db.get_setting("maintenance")
    if maintenance == "1":
        return False
    return True


async def poll_sms(
    bot,
    chat_id: int,
    activation_id: str,
    phone: str,
    client: HeroSMSClient,
):
    """Background task: poll until OTP arrives (up to ~10 min)."""
    for _ in range(200):
        await asyncio.sleep(3)
        try:
            res = await client.get_status(activation_id)
            if isinstance(res, str):
                if res.startswith("STATUS_OK:"):
                    code = res.split(":", 1)[1]
                    text = f"\U0001F4F1 **Number:** `+{phone}`\n\U0001F4AC **OTP:** `{code}`"
                    await bot.send_message(
                        chat_id,
                        text,
                        reply_markup=kb.otp_copy_menu(code),
                        parse_mode="Markdown",
                    )
                    await client.set_status(activation_id, 6)
                    return
                if res.startswith("STATUS_CANCEL"):
                    return
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await db.add_user(message.from_user.id)
    user = await db.get_user(message.from_user.id)

    if user and user["is_banned"]:
        await message.answer("You are banned from using this bot.")
        return

    maintenance = await db.get_setting("maintenance")
    if maintenance == "1" and message.from_user.id != ADMIN_ID:
        await message.answer(
            "\U0001F6E0 Bot is under maintenance. Contact @Syedmahinislam."
        )
        return

    if not user or not user["api_key"]:
        await message.answer(
            "Welcome to HeroSMS Bot!\n\n"
            "Please send your HeroSMS API Key to get started."
        )
        await state.set_state(BotStates.waiting_for_api_key)
    else:
        await message.answer(
            "Welcome back! \U0001F44B",
            reply_markup=kb.main_reply_menu(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# API Key setup
# ─────────────────────────────────────────────────────────────────────────────
@router.message(BotStates.waiting_for_api_key)
async def process_api_key(message: Message, state: FSMContext):
    api_key = message.text.strip()
    client  = HeroSMSClient(api_key)
    balance = await client.get_balance()
    if balance is not None:
        await db.update_api_key(message.from_user.id, api_key)
        await state.clear()
        await message.answer(
            "\u2705 API Key saved successfully!",
            reply_markup=kb.main_reply_menu(),
        )
    else:
        await message.answer(
            "\u274C Invalid API Key. Please check and try again."
        )


# ─────────────────────────────────────────────────────────────────────────────
# menu_main callback (go back to home)
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu_main")
async def cb_menu_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not await is_allowed(callback.from_user.id):
        await callback.answer("Not allowed.", show_alert=True)
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "Welcome back! \U0001F44B",
        reply_markup=kb.main_reply_menu(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────
@router.message(F.text == "\U0001F464 Profile")
async def text_profile(message: Message):
    if not await is_allowed(message.from_user.id):
        return
    user = await db.get_user(message.from_user.id)
    if not user or not user["api_key"]:
        await message.answer("API Key not set. Use /start to set it.")
        return
    client  = HeroSMSClient(user["api_key"])
    balance = await client.get_balance()
    bal_str = f"{balance:.4f} USD" if balance is not None else "Error"
    text = (
        f"\U0001F464 **Profile**\n\n"
        f"\U0001F4B0 **Balance:** {bal_str}\n"
        f"\U0001F511 **API Key:** `{user['api_key'][:12]}...`"
    )
    await message.answer(text, reply_markup=kb.profile_menu(), parse_mode="Markdown")


@router.callback_query(F.data == "profile_change_key")
async def cb_change_key(callback: CallbackQuery, state: FSMContext):
    if not await is_allowed(callback.from_user.id):
        await callback.answer("Not allowed.", show_alert=True)
        return
    await callback.message.edit_text(
        "Please send your new HeroSMS API Key.", reply_markup=kb.back_button()
    )
    await state.set_state(BotStates.waiting_for_api_key)


# ─────────────────────────────────────────────────────────────────────────────
# Balance
# ─────────────────────────────────────────────────────────────────────────────
@router.message(F.text == "\U0001F4B0 Balance")
async def text_balance(message: Message):
    if not await is_allowed(message.from_user.id):
        return
    user = await db.get_user(message.from_user.id)
    if not user or not user["api_key"]:
        await message.answer("API Key not set.")
        return
    client  = HeroSMSClient(user["api_key"])
    balance = await client.get_balance()
    if balance is not None:
        await message.answer(
            f"\U0001F4B0 **Balance:** `{balance:.4f} USD`", parse_mode="Markdown"
        )
    else:
        await message.answer("\u274C Error fetching balance.")


# ─────────────────────────────────────────────────────────────────────────────
# Support
# ─────────────────────────────────────────────────────────────────────────────
@router.message(F.text == "\U0001F4AC Support")
async def text_support(message: Message):
    await message.answer(
        "\U0001F4DE **Support:** @Syedmahinislam", parse_mode="Markdown"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Buy single Telegram number
# ─────────────────────────────────────────────────────────────────────────────
@router.message(F.text == "\U0001F4F1 Buy Telegram Number")
async def text_buy_tg_number(message: Message):
    if not await is_allowed(message.from_user.id):
        return
    user = await db.get_user(message.from_user.id)
    if not user or not user["api_key"]:
        await message.answer("API Key not set.")
        return
    client = HeroSMSClient(user["api_key"])
    prices = await client.get_prices(country=COLOMBIA_ID, service=TG_SERVICE)
    try:
        cost  = prices[str(COLOMBIA_ID)][TG_SERVICE]["cost"]
        count = prices[str(COLOMBIA_ID)][TG_SERVICE]["count"]
    except (KeyError, TypeError):
        await message.answer("\u274C Pricing not available right now.")
        return
    text = (
        f"\U0001F6D2 **Purchase Info**\n\n"
        f"\U0001F30D Country: Colombia\n"
        f"\U0001F4F1 Service: Telegram\n\n"
        f"\U0001F4B0 Price: `{cost} USD`\n"
        f"\U0001F4E6 Available: `{count}` numbers\n\n"
        f"Do you want to buy?"
    )
    await message.answer(
        text,
        reply_markup=kb.confirm_number_menu(COLOMBIA_ID, TG_SERVICE),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("buy_"))
async def cb_buy_number(callback: CallbackQuery):
    parts      = callback.data.split("_")
    country_id = parts[1]
    service    = parts[2]

    user   = await db.get_user(callback.from_user.id)
    client = HeroSMSClient(user["api_key"])

    await callback.message.edit_text("\u23F3 Buying number...")

    res = await client.get_number(service=service, country=country_id, max_price=MAX_PRICE)

    if not isinstance(res, dict) or "activationId" not in res:
        err = res.get("title", str(res)) if isinstance(res, dict) else str(res)
        await callback.message.edit_text(f"\u274C Failed: {err}")
        return

    activation_id = str(res["activationId"])
    phone         = res.get("phoneNumber", "Unknown")
    cost          = res.get("activationCost", "?")

    text = (
        f"\u2705 **Number Purchased!**\n\n"
        f"\U0001F4F1 **Phone:** `+{phone}`\n"
        f"\U0001F4B0 **Cost:** `{cost} USD`\n\n"
        f"Waiting for SMS..."
    )
    await callback.message.edit_text(
        text,
        reply_markup=kb.number_action_menu(activation_id),
        parse_mode="Markdown",
    )
    asyncio.create_task(
        poll_sms(callback.bot, callback.message.chat.id, activation_id, phone, client)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Check SMS manually
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("check_"))
async def cb_check_sms(callback: CallbackQuery):
    activation_id = callback.data[len("check_"):]
    user   = await db.get_user(callback.from_user.id)
    client = HeroSMSClient(user["api_key"])
    res    = await client.get_status(activation_id)

    if isinstance(res, str):
        if res.startswith("STATUS_OK:"):
            code = res.split(":", 1)[1]
            await callback.message.edit_text(
                f"\U0001F4E9 **OTP Received!**\n\n`{code}`",
                reply_markup=kb.otp_copy_menu(code),
                parse_mode="Markdown",
            )
            await client.set_status(activation_id, 6)
        elif res.startswith("STATUS_WAIT_CODE"):
            await callback.answer("Still waiting for SMS...", show_alert=True)
        elif res.startswith("STATUS_CANCEL"):
            await callback.message.edit_text(
                "\u274C Activation cancelled.",
                reply_markup=kb.back_button(),
            )
        else:
            await callback.answer(f"Status: {res}", show_alert=True)
    else:
        await callback.answer("Error checking status.", show_alert=True)


# ─────────────────────────────────────────────────────────────────────────────
# Cancel single number
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("single_cancel_"))
async def cb_cancel_single(callback: CallbackQuery):
    activation_id = callback.data[len("single_cancel_"):]
    user   = await db.get_user(callback.from_user.id)
    client = HeroSMSClient(user["api_key"])
    res    = await client.set_status(activation_id, 8)

    if isinstance(res, str) and res.startswith("ACCESS_CANCEL"):
        await callback.message.edit_text(
            "\u2705 Cancelled. Balance refunded.",
            reply_markup=kb.back_button(),
        )
    elif isinstance(res, str) and "EARLY_CANCEL_DENIED" in res:
        await callback.answer(
            "Cannot cancel within first 2 minutes.", show_alert=True
        )
    else:
        err = res.get("title", str(res)) if isinstance(res, dict) else str(res)
        await callback.answer(f"Error: {err}", show_alert=True)


# ─────────────────────────────────────────────────────────────────────────────
# Bulk buy
# ─────────────────────────────────────────────────────────────────────────────
@router.message(F.text == "\U0001F4E6 Bulk Buy Numbers")
async def text_bulk_buy(message: Message, state: FSMContext):
    if not await is_allowed(message.from_user.id):
        return
    user = await db.get_user(message.from_user.id)
    if not user or not user["api_key"]:
        await message.answer("API Key not set.")
        return
    await message.answer(
        "\U0001F522 **Bulk Purchase**\n\nHow many numbers do you want to buy? (1\u2013500)",
        parse_mode="Markdown",
    )
    await state.set_state(BotStates.waiting_for_bulk_amount)


@router.message(BotStates.waiting_for_bulk_amount)
async def process_bulk_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if not (1 <= amount <= 500):
            raise ValueError
    except ValueError:
        await message.answer("\u26A0\uFE0F Enter a number between 1 and 500.")
        return

    await state.clear()
    user   = await db.get_user(message.from_user.id)
    client = HeroSMSClient(user["api_key"])

    status_msg = await message.answer(
        f"\U0001F504 Buying **{amount}** numbers... please wait.",
        parse_mode="Markdown",
    )

    purchased = []
    for i in range(amount):
        res = await client.get_number(
            service=TG_SERVICE, country=COLOMBIA_ID, max_price=MAX_PRICE
        )
        if isinstance(res, dict) and "activationId" in res:
            aid   = str(res["activationId"])
            phone = res.get("phoneNumber", "Unknown")
            purchased.append(phone)
            asyncio.create_task(
                poll_sms(message.bot, message.chat.id, aid, phone, client)
            )
            if len(purchased) % 5 == 0:
                try:
                    await status_msg.edit_text(
                        f"\U0001F504 Bought **{len(purchased)}/{amount}** numbers...",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass
            await asyncio.sleep(0.3)
        else:
            err = res.get("title", str(res)) if isinstance(res, dict) else str(res)
            await message.answer(f"\u274C Stopped at #{i+1}: {err}")
            break

    if purchased:
        lines = "\n".join(f"{n}. `+{p}`" for n, p in enumerate(purchased, 1))
        final = (
            f"\u2705 **Bulk Order Done!**\n\n"
            f"Purchased **{len(purchased)}** numbers:\n\n{lines}"
        )
        if len(final) > 4000:
            parts = [final[i:i+4000] for i in range(0, len(final), 4000)]
            for part in parts:
                await message.answer(part, parse_mode="Markdown")
            await status_msg.delete()
        else:
            await status_msg.edit_text(final, parse_mode="Markdown")
    else:
        await status_msg.edit_text("\u274C Could not purchase any numbers.")


# ─────────────────────────────────────────────────────────────────────────────
# Active numbers & cancel all
# ─────────────────────────────────────────────────────────────────────────────
@router.message(F.text == "\u26A1 Active Numbers")
async def text_active_numbers(message: Message):
    if not await is_allowed(message.from_user.id):
        return
    user = await db.get_user(message.from_user.id)
    if not user or not user["api_key"]:
        await message.answer("API Key not set.")
        return

    client     = HeroSMSClient(user["api_key"])
    status_msg = await message.answer("\U0001F504 Fetching active numbers...")
    res        = await client.get_active_activations()

    if not (isinstance(res, dict) and res.get("status") == "success"):
        err = res.get("title", str(res)) if isinstance(res, dict) else str(res)
        await status_msg.edit_text(f"\u274C Error: {err}")
        return

    activations = res.get("data", [])
    if not activations:
        await status_msg.edit_text("\u2705 No active numbers.")
        return

    lines = "\n".join(
        f"\U0001F539 `+{a.get('phoneNumber')}` (ID: {a.get('activationId')})"
        for a in activations
    )
    text = f"\U0001F4F1 **Active Numbers ({len(activations)}):**\n\n{lines}"
    if len(text) > 4000:
        text = text[:3990] + "\n...(truncated)"

    await status_msg.edit_text(
        text,
        reply_markup=kb.cancel_all_menu(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "cancel_all_active")
async def cb_cancel_all_active(callback: CallbackQuery):
    if not await is_allowed(callback.from_user.id):
        return
    user   = await db.get_user(callback.from_user.id)
    client = HeroSMSClient(user["api_key"])

    res = await client.get_active_activations()
    if not (isinstance(res, dict) and res.get("status") == "success"):
        await callback.answer("Failed to fetch active numbers.", show_alert=True)
        return

    activations = res.get("data", [])
    if not activations:
        await callback.answer("No active numbers to cancel.", show_alert=True)
        return

    await callback.message.edit_text(
        f"\U0001F504 Cancelling {len(activations)} numbers... please wait.",
        parse_mode="Markdown",
    )

    async def cancel_one(act):
        aid = str(act.get("activationId", ""))
        if not aid:
            return False
        try:
            r = await client.set_status(aid, 8)
            if isinstance(r, str) and (
                r.startswith("ACCESS_CANCEL") or r.startswith("STATUS_CANCEL")
            ):
                return True
            if isinstance(r, dict) and r.get("status") == "success":
                return True
        except Exception:
            pass
        return False

    results = await asyncio.gather(*[cancel_one(a) for a in activations])
    ok = sum(1 for x in results if x)

    await callback.message.edit_text(
        f"\u2705 Cancelled **{ok}/{len(activations)}** numbers. Balance refunded.",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────────────────────────────────────
# noop callback (for fallback copy button)
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Admin: /admin
# ─────────────────────────────────────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    maintenance = await db.get_setting("maintenance")
    await message.answer(
        "Admin Panel", reply_markup=kb.admin_menu(maintenance == "1")
    )


@router.callback_query(F.data == "admin_maintenance")
async def cb_admin_maintenance(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    current = await db.get_setting("maintenance")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("maintenance", new_val)
    await callback.message.edit_reply_markup(
        reply_markup=kb.admin_menu(new_val == "1")
    )
    await callback.answer("Maintenance updated.")


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer(
        "Send the broadcast message:", reply_markup=kb.back_button()
    )
    await state.set_state(BotStates.waiting_for_broadcast)


@router.message(BotStates.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    users = await db.get_all_users()
    sent  = 0
    for uid in users:
        try:
            await message.bot.send_message(
                uid,
                f"\U0001F4E2 **Broadcast:**\n\n{message.text}",
                parse_mode="Markdown",
            )
            sent += 1
        except Exception:
            pass
    await message.answer(f"\u2705 Sent to {sent} users.")
    await state.clear()


@router.callback_query(F.data == "admin_ban")
async def cb_admin_ban(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer(
        "Send the user ID to ban/unban:", reply_markup=kb.back_button()
    )
    await state.set_state(BotStates.waiting_for_ban_id)


@router.message(BotStates.waiting_for_ban_id)
async def process_ban_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target = int(message.text.strip())
    except ValueError:
        await message.answer("Invalid ID.")
        return
    user = await db.get_user(target)
    if not user:
        await message.answer("User not found.")
        return
    new_status = not bool(user["is_banned"])
    await db.set_ban_status(target, new_status)
    label = "Banned" if new_status else "Unbanned"
    await message.answer(f"\u2705 User {target} {label}.")
    await state.clear()
