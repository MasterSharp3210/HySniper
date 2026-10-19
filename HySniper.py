from datetime import datetime, timezone
import json
from pathlib import Path
import time
import requests

HYPIXEL_API_KEY = "API_KEY_HERE"  # Replace with your Hypixel API key (https://developer.hypixel.net)
DISCORD_WEBHOOK_URL = "DISCORD_WEBHOOK_URL_HERE"  # Replace with your Discord webhook URL (https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks)
CHECK_INTERVAL = 60

HYPIXEL_API_URL = "https://api.hypixel.net/v2/player"
MOJANG_API_URL = "https://api.mojang.com/users/profiles/minecraft/{}"
STATE_FILE = Path("bedwars_stats.json")

session = requests.Session()
session.headers.update({"User-Agent": "BedWarsStatsBot/1.0"})


def send_embed(player_name, title, description, color):
    payload = {
        "username": "BedWars Stats Tracker",
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "footer": {"text": f"Hypixel BedWars | {player_name}"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "allowed_mentions": {"parse": []},
    }

    try:
        response = session.post(
            DISCORD_WEBHOOK_URL, json=payload, timeout=15
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


def get_uuid(username):
    try:
        response = session.get(MOJANG_API_URL.format(username), timeout=15)
        if response.status_code != 200:
            return None
        return response.json().get("id")
    except (requests.RequestException, ValueError):
        return None


def fetch_stats(uuid):
    try:
        response = session.get(
            HYPIXEL_API_URL,
            headers={"API-Key": HYPIXEL_API_KEY},
            params={"uuid": uuid},
            timeout=15,
        )

        if response.status_code != 200:
            return None

        data = response.json()
        player = data.get("player")

        if not data.get("success") or not player:
            return None

        bedwars = player.get("stats", {}).get("Bedwars", {})

        if not bedwars:
            return None

        final_kills = int(bedwars.get("final_kills_bedwars", 0))
        final_deaths = int(bedwars.get("final_deaths_bedwars", 0))
        kills = int(bedwars.get("kills_bedwars", 0))
        deaths = int(bedwars.get("deaths_bedwars", 0))
        beds_broken = int(bedwars.get("beds_broken_bedwars", 0))
        beds_lost = int(bedwars.get("beds_lost_bedwars", 0))
        wins = int(bedwars.get("wins_bedwars", 0))
        winstreak = bedwars.get("winstreak")

        last_login = player.get("lastLogin", 0)
        last_logout = player.get("lastLogout", 0)
        is_online = last_login > last_logout

        return {
            "FKDR": round(
                final_kills / final_deaths if final_deaths else final_kills, 2
            ),
            "WS": int(winstreak) if winstreak is not None else None,
            "KDR": round(
                kills / deaths if deaths else kills, 2
            ),
            "BBLR": round(
                beds_broken / beds_lost if beds_lost else beds_broken, 2
            ),
            "final_kills": final_kills,
            "kills": kills,
            "beds_broken": beds_broken,
            "wins": wins,
            "online": is_online,
        }

    except (requests.RequestException, ValueError, TypeError, KeyError):
        return None


def load_stats():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return None


def save_stats(stats):
    try:
        STATE_FILE.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    except OSError:
        pass


def format_value(value):
    return "N/A" if value is None else str(value)


def build_recap(current):
    status_emoji = "🟢 Online" if current.get("online") else "🔴 Offline"
    return (
        f"🌐 **Status:** `{status_emoji}`\n"
        f"🎯 **FKDR:** `{format_value(current['FKDR'])}`\n"
        f"🔥 **WS:** `{format_value(current['WS'])}`\n"
        f"⚔️ **KDR:** `{format_value(current['KDR'])}`\n"
        f"🛏️ **BBLR:** `{format_value(current['BBLR'])}`"
    )


def build_update(previous, current):
    changes = []
    has_increase = False
    has_decrease = False

    config = {
        "FKDR": ("🎯", 2),
        "WS": ("🔥", 0),
        "KDR": ("⚔️", 2),
        "BBLR": ("🛏️", 2),
    }

    for stat, (emoji, decimals) in config.items():
        old = previous.get(stat)
        new = current.get(stat)

        if old is None or new is None or old == new:
            continue

        difference = new - old
        arrow = "📈" if difference > 0 else "📉"

        if difference > 0:
            has_increase = True
        else:
            has_decrease = True

        sign = "+" if difference > 0 else ""
        delta = f"{sign}{difference:.{decimals}f}"

        changes.append(
            f"{arrow} **{emoji} {stat}**\n`{old}` → `{new}` (`{delta}`)"
        )

    if not changes:
        return None

    if has_increase and has_decrease:
        title = "📊 BEDWARS STATS UPDATE"
        color = 0xF1C40F
    elif has_increase:
        title = "📈 BEDWARS STATS INCREASED"
        color = 0x2ECC71
    else:
        title = "📉 BEDWARS STATS DECREASED"
        color = 0xE74C3C

    description = (
        "### 🔔 Changes Detected\n"
        + "\n\n".join(changes)
        + "\n\n━━━━━━━━━━━━━━━━━━\n"
        + "### 👤 CURRENT STATS\n"
        + build_recap(current)
    )

    return title, description, color


def send_win_notifications(player_name, previous, current):
    old_ws = previous.get("WS")
    new_ws = current.get("WS")

    if old_ws is None or new_ws is None or new_ws <= old_ws:
        return

    wins_detected = new_ws - old_ws

    for index in range(wins_detected):
        streak = old_ws + index + 1
        description = (
            f"🏆 **Victory detected for {player_name}!**\n\n"
            f"🔥 **Win Streak:** `{streak - 1}` → `{streak}`\n"
            f"🎉 **Win #{index + 1} detected since the last check**\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "### 👤 CURRENT STATS\n"
            + build_recap(current)
        )
        send_embed(player_name, "🏆 BEDWARS VICTORY!", description, 0x2ECC71)


def normal_mode_loop(player_name, uuid):
    previous = load_stats()
    while True:
        try:
            current = fetch_stats(uuid)
            if current is not None:
                if previous is None:
                    previous = current
                    save_stats(current)
                else:
                    send_win_notifications(player_name, previous, current)
                    update = build_update(previous, current)
                    if update:
                        title, description, color = update
                        send_embed(player_name, title, description, color)
                    save_stats(current)
                    previous = current
        except Exception:
            pass
        time.sleep(CHECK_INTERVAL)


def extreme_mode_loop(player_name, uuid):
    previous = load_stats()
    while True:
        try:
            current = fetch_stats(uuid)
            if current is not None:
                if previous is None:
                    previous = current
                    save_stats(current)
                else:
                    wins_diff = current["wins"] - previous.get("wins", current["wins"])
                    beds_diff = current["beds_broken"] - previous.get("beds_broken", current["beds_broken"])
                    fk_diff = current["final_kills"] - previous.get("final_kills", current["final_kills"])
                    kills_diff = current["kills"] - previous.get("kills", current["kills"])

                    if wins_diff > 0:
                        for _ in range(wins_diff):
                            desc = (
                                f"🏆 **Victory detected for {player_name}!**\n\n"
                                "━━━━━━━━━━━━━━━━━━\n"
                                "### 👤 CURRENT STATS\n"
                                + build_recap(current)
                            )
                            send_embed(player_name, "🏆 BEDWARS VICTORY!", desc, 0x2ECC71)

                    if beds_diff > 0:
                        for _ in range(beds_diff):
                            desc = (
                                f"🛏️ **Bed broken by {player_name}!**\n\n"
                                "━━━━━━━━━━━━━━━━━━\n"
                                "### 👤 CURRENT STATS\n"
                                + build_recap(current)
                            )
                            send_embed(player_name, "🛏️ BED BROKEN!", desc, 0x3498DB)

                    if fk_diff > 0:
                        for _ in range(fk_diff):
                            desc = (
                                f"🎯 **Final Kill by {player_name}!**\n\n"
                                "━━━━━━━━━━━━━━━━━━\n"
                                "### 👤 CURRENT STATS\n"
                                + build_recap(current)
                            )
                            send_embed(player_name, "🎯 FINAL KILL!", desc, 0x9B59B6)

                    if kills_diff > 0:
                        for _ in range(kills_diff):
                            desc = (
                                f"⚔️ **Kill by {player_name}!**\n\n"
                                "━━━━━━━━━━━━━━━━━━\n"
                                "### 👤 CURRENT STATS\n"
                                + build_recap(current)
                            )
                            send_embed(player_name, "⚔️ KILL!", desc, 0xE67E22)

                    save_stats(current)
                    previous = current
        except Exception:
            pass
        time.sleep(CHECK_INTERVAL)


def main():
    print("=== BedWars Stats Bot ===")
    player_name = input("Enter the Minecraft username to track: ").strip()
    if not player_name:
        print("Invalid username. Exiting.")
        return

    print("\nSelect Bot Mode:")
    print("1) Normal mode")
    print("2) Extreme mode")
    
    choice = input("Enter your choice (1 or 2): ").strip()
    
    if choice == "2":
        print(f"Starting bot for '{player_name}' in EXTREME MODE...", flush=True)
        mode = "extreme"
    else:
        print(f"Starting bot for '{player_name}' in NORMAL MODE...", flush=True)
        mode = "normal"

    if (
        not HYPIXEL_API_KEY
        or HYPIXEL_API_KEY == "API_KEY_HERE"
        or not DISCORD_WEBHOOK_URL
        or DISCORD_WEBHOOK_URL == "DISCORD_WEBHOOK_URL_HERE"
    ):
        print("Please configure your API Key and Webhook URL in the script!")
        while True:
            time.sleep(CHECK_INTERVAL)

    uuid = None
    while uuid is None:
        uuid = get_uuid(player_name)
        if uuid is None:
            print(f"Failed to fetch UUID for {player_name}. Retrying in {CHECK_INTERVAL}s...")
            time.sleep(CHECK_INTERVAL)

    print(f"Successfully fetched UUID for {player_name}: {uuid}", flush=True)

    if mode == "extreme":
        extreme_mode_loop(player_name, uuid)
    else:
        normal_mode_loop(player_name, uuid)


if __name__ == "__main__":
    main()
