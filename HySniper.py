from datetime import datetime, timezone
import json
from pathlib import Path
import time
import requests

HYPIXEL_API_KEY = "HYPIXEL_API_KEY" # Replace with your Hypixel API Key
DISCORD_WEBHOOK_URL = "DISCORD_WEBHOOK_URL" # Replace with your Hypixel API Key
CHECK_INTERVAL = 15

HYPIXEL_PLAYER_URL = "https://api.hypixel.net/v2/player"
HYPIXEL_STATUS_URL = "https://api.hypixel.net/v2/status"
MOJANG_API_URL = "https://api.mojang.com/users/profiles/minecraft/{}"
STATE_FILE = Path("bedwars_stats.json")

session = requests.Session()
session.headers.update({"User-Agent": "BedWarsStatsBot/1.0"})

MODE_MAPPING = {
    "BEDWARS_EIGHT_ONE": "Solo (1v1v1v1v1v1v1v1)",
    "BEDWARS_EIGHT_TWO": "Doubles (2v2v2v2v2v2v2v2)",
    "BEDWARS_FOUR_THREE": "3v3v3v3",
    "BEDWARS_FOUR_FOUR": "4v4v4v4",
    "BEDWARS_TWO_FOUR": "4v4",
    "BEDWARS_EIGHT_ONE_RUSH": "Rush Solo",
    "BEDWARS_FOUR_FOUR_RUSH": "Rush 4v4v4v4",
    "BEDWARS_EIGHT_ONE_ULTIMATE": "Ultimate Solo",
    "BEDWARS_FOUR_FOUR_ULTIMATE": "Ultimate 4v4v4v4",
    "BEDWARS_CASTLE": "Castle 40v40",
}

def test_connections(player_name, uuid):
    print(f"[LOG] Testing Discord webhook connection...", flush=True)
    try:
        response = session.post(DISCORD_WEBHOOK_URL, json={"content": ""}, timeout=15)
        print(f"[LOG] Discord webhook test response code: {response.status_code}", flush=True)
    except requests.RequestException as e:
        print(f"[LOG] Discord webhook test error: {e}", flush=True)

    print(f"[LOG] Testing Hypixel API connection for UUID: {uuid}...", flush=True)
    try:
        response = session.get(
            HYPIXEL_PLAYER_URL,
            headers={"API-Key": HYPIXEL_API_KEY},
            params={"uuid": uuid},
            timeout=15,
        )
        print(f"[LOG] Hypixel API test response code: {response.status_code}", flush=True)
    except requests.RequestException as e:
        print(f"[LOG] Hypixel API test error: {e}", flush=True)

def send_embed(title, description, color, player_name):
    print(f"[LOG] Sending Discord notification -> [{title}]", flush=True)
    payload = {
        "username": "BedWars Tracker",
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
        print("[LOG] Discord notification sent successfully.", flush=True)
        return True
    except requests.RequestException as e:
        print(f"[LOG] ERROR: Failed to send Discord notification: {e}", flush=True)
        return False

def get_uuid(username):
    print(f"[LOG] Fetching UUID for username: {username}", flush=True)
    try:
        response = session.get(MOJANG_API_URL.format(username), timeout=15)
        if response.status_code != 200:
            print(f"[LOG] Failed to fetch UUID. Status code: {response.status_code}", flush=True)
            return None
        uuid = response.json().get("id")
        print(f"[LOG] Successfully retrieved UUID: {uuid}", flush=True)
        return uuid
    except (requests.RequestException, ValueError) as e:
        print(f"[LOG] ERROR while fetching UUID: {e}", flush=True)
        return None

def fetch_status(uuid):
    print(f"[LOG] Fetching player status from Hypixel API...", flush=True)
    try:
        response = session.get(
            HYPIXEL_STATUS_URL,
            headers={"API-Key": HYPIXEL_API_KEY},
            params={"uuid": uuid},
            timeout=15,
        )
        print(f"[LOG] Status API HTTP Code: {response.status_code}", flush=True)
        if response.status_code != 200:
            return None

        data = response.json()
        print(f"[LOG] Status API Raw JSON Response: {data}", flush=True)
        if not data.get("success"):
            return None

        return data.get("session")
    except (requests.RequestException, ValueError) as e:
        print(f"[LOG] Error fetching status: {e}", flush=True)
        return None

def fetch_stats(uuid):
    print(f"[LOG] Fetching player stats from Hypixel API...", flush=True)
    try:
        response = session.get(
            HYPIXEL_PLAYER_URL,
            headers={"API-Key": HYPIXEL_API_KEY},
            params={"uuid": uuid},
            timeout=15,
        )

        if response.status_code != 200:
            print(f"[LOG] Stats API HTTP Code: {response.status_code}", flush=True)
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
        winstreak = bedwars.get("winstreak")

        return {
            "FKDR": round(
                final_kills / final_deaths if final_deaths else final_kills, 2
            ),
            "WS": int(winstreak) if winstreak is not None else None,
            "KDR": round(kills / deaths if deaths else kills, 2),
            "BBLR": round(
                beds_broken / beds_lost if beds_lost else beds_broken, 2
            ),
        }
    except (requests.RequestException, ValueError, TypeError, KeyError) as e:
        print(f"[LOG] Error fetching stats: {e}", flush=True)
        return None

def load_stats():
    try:
        if STATE_FILE.exists():
            print("[LOG] Loading previous stats from local file...", flush=True)
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

def build_status_report(is_online, game_type, mode_formatted, map_name, previous, current):
    status_emoji = "🟢" if is_online else "🔴"
    status_text = "Online" if is_online else "Offline"
    
    description = (
        f"**Status:** `{status_emoji} {status_text}`\n"
        f"📌 **Mode:** `{mode_formatted}`\n"
        f"🗺️ **Map:** `{map_name}`\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "### 👤 STATS & CHANGES\n"
    )

    if current is None:
        description += "Could not fetch current stats."
        return "📊 BEDWARS STATUS REPORT", description, 0x95A5A6

    config = {
        "FKDR": ("🎯", 2),
        "WS": ("🔥", 0),
        "KDR": ("⚔️", 2),
        "BBLR": ("🛏️", 2),
    }

    stat_lines = []
    has_increase = False
    has_decrease = False

    for stat, (emoji, decimals) in config.items():
        new = current.get(stat)
        old = previous.get(stat) if previous else None

        val_str = f"`{format_value(new)}`"
        if old is not None and new is not None and old != new:
            diff = new - old
            arrow = "📈" if diff > 0 else "📉"
            if diff > 0:
                has_increase = True
            else:
                has_decrease = True
            sign = "+" if diff > 0 else ""
            delta = f"{sign}{diff:.{decimals}f}"
            val_str = f"`{old}` → `{new}` (`{arrow} {delta}`)"

        stat_lines.append(f"{emoji} **{stat}:** {val_str}")

    description += "\n".join(stat_lines)

    if has_increase and has_decrease:
        title = "📊 BEDWARS STATUS & STATS UPDATE"
        color = 0xF1C40F
    elif has_increase:
        title = "📈 BEDWARS STATUS & STATS INCREASED"
        color = 0x2ECC71
    elif has_decrease:
        title = "📉 BEDWARS STATUS & STATS DECREASED"
        color = 0xE74C3C
    else:
        title = "📊 BEDWARS STATUS REPORT"
        color = 0x3498DB

    return title, description, color

def main():
    print("=== HySniper v.2.0.0 ===")
    player_name = input("Enter Minecraft Username to track: ").strip()
    if not player_name:
        print("[LOG] No username provided. Exiting.", flush=True)
        return

    print(f"[LOG] Initializing tracker for target: {player_name}", flush=True)

    uuid = None
    while uuid is None:
        uuid = get_uuid(player_name)
        if uuid is None:
            print("[LOG] Retrying UUID fetch in 5 seconds...", flush=True)
            time.sleep(5)

    test_connections(player_name, uuid)

    print(f"[LOG] Tracking started for {player_name} (UUID: {uuid})", flush=True)

    previous_stats = load_stats()

    while True:
        try:
            print("[LOG] Checking player status and stats...", flush=True)
            status = fetch_status(uuid)
            
            is_online = False
            game_type = "Offline/Unknown"
            mode_raw = "Lobby"
            map_name = "Lobby"
            mode_formatted = "Lobby / Waiting Room"

            if status:
                is_online = status.get("online", False)
                if is_online:
                    game_type = status.get("gameType", "Lobby")
                    mode_raw = status.get("mode", "Lobby")
                    map_name = status.get("map", "Lobby")
                    if not map_name:
                        map_name = "Lobby"
                    if not mode_raw:
                        mode_raw = "Lobby"
                    mode_formatted = MODE_MAPPING.get(mode_raw, mode_raw)

            print(f"[CONSOLE] Status -> Online: {is_online} | Game: {game_type} | Mode: {mode_formatted} | Map: {map_name}", flush=True)

            current_stats = fetch_stats(uuid)

            if current_stats is not None:
                print(f"[CONSOLE] Stats -> {current_stats}", flush=True)
                if previous_stats is None:
                    previous_stats = current_stats
                    save_stats(current_stats)

                title, description, color = build_status_report(is_online, game_type, mode_formatted, map_name, previous_stats, current_stats)
                send_embed(title, description, color, player_name)

                save_stats(current_stats)
                previous_stats = current_stats
            else:
                print("[LOG] Could not fetch current player stats.", flush=True)
                title, description, color = build_status_report(is_online, game_type, mode_formatted, map_name, previous_stats, None)
                send_embed(title, description, color, player_name)

        except Exception as e:
            print(f"[LOG] ERROR in main loop: {e}", flush=True)

        print(f"[LOG] Waiting {CHECK_INTERVAL} seconds for the next check...\n", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
