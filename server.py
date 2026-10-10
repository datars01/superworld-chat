import asyncio
import json
import uuid
import colorsys
import os
import websockets

clients = {}
players = {}
chat_history = []

PALETTE = [
    "#FF595E", "#1982C4", "#8AC926", "#FFCA3A",
    "#6A4C93", "#F15BB5", "#00BBF9", "#00F5D4",
    "#E76F51", "#4361EE", "#B5179E", "#2A9D8F",
    "#F77F00", "#7209B7", "#3A86FF", "#588157",
    "#D62828", "#8338EC", "#06D6A0", "#FB5607",
]


async def send_to_client(client, data):
    await client.send(json.dumps(data, ensure_ascii=False))


async def broadcast(data, exclude=None):
    message = json.dumps(data, ensure_ascii=False)
    disconnected = []

    for client in list(clients):
        if client == exclude:
            continue
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosed:
            disconnected.append(client)

    for client in disconnected:
        player_id = clients.pop(client, None)
        if player_id:
            info = players.pop(player_id, None)
            if info:
                await broadcast({"type": "left", "id": player_id})


def choose_color():
    used = {p["color"] for p in players.values()}

    for color in PALETTE:
        if color not in used:
            return color

    # If the palette is full, generate another unused color.
    for i in range(360):
        hue = (i * 137.508) % 360
        r, g, b = colorsys.hsv_to_rgb(hue / 360, 0.72, 0.98)
        color = "#{:02X}{:02X}{:02X}".format(
            round(r * 255), round(g * 255), round(b * 255)
        )
        if color not in used:
            return color

    return "#FFFFFF"


async def handle_client(websocket):
    player_id = uuid.uuid4().hex
    clients[websocket] = player_id
    joined = False

    print(f"🟢 اتصال جديد | الاتصالات: {len(clients)}")

    try:
        await send_to_client(websocket, {
            "type": "welcome",
            "id": player_id,
            "players": [
                {
                    "id": pid,
                    "name": info["name"],
                    "x": info["x"],
                    "y": info["y"],
                    "color": info["color"],
                }
                for pid, info in players.items()
            ],
            "history": chat_history[-100:],
        })

        async for raw_message in websocket:
            try:
                data = json.loads(raw_message)
                if not isinstance(data, dict):
                    continue

                msg_type = data.get("type")

                if msg_type == "join":
                    name = str(data.get("name", "")).strip()
                    name = name[:20]

                    if not name:
                        await send_to_client(websocket, {
                            "type": "name_error",
                            "message": "اكتب يوزر قبل الدخول"
                        })
                        continue

                    if joined:
                        continue

                    duplicate = any(
                        info["name"].casefold() == name.casefold()
                        for pid, info in players.items()
                        if pid != player_id
                    )

                    if duplicate:
                        await send_to_client(websocket, {
                            "type": "name_error",
                            "message": "هذا اليوزر مستخدم حالياً، اختار غيره"
                        })
                        continue

                    color = choose_color()
                    players[player_id] = {
                        "name": name,
                        "x": 0.5,
                        "y": 0.65,
                        "color": color,
                    }
                    joined = True

                    await send_to_client(websocket, {
                        "type": "joined",
                        "id": player_id,
                        "name": name,
                        "color": color,
                    })

                    await broadcast({
                        "type": "player_joined",
                        "id": player_id,
                        "name": name,
                        "x": 0.5,
                        "y": 0.65,
                        "color": color,
                    }, exclude=websocket)

                    print(f"👤 دخل {name} | اللون: {color}")
                    continue

                if not joined or player_id not in players:
                    continue

                if msg_type == "position":
                    try:
                        x = max(0.0, min(1.0, float(data["x"])))
                        y = max(0.0, min(1.0, float(data["y"])))
                    except (KeyError, TypeError, ValueError):
                        continue

                    players[player_id]["x"] = x
                    players[player_id]["y"] = y

                    await broadcast({
                        "type": "position",
                        "id": player_id,
                        "name": players[player_id]["name"],
                        "x": x,
                        "y": y,
                        "color": players[player_id]["color"],
                    }, exclude=websocket)

                elif msg_type == "chat":
                    message = str(data.get("message", "")).strip()[:500]
                    if not message:
                        continue

                    entry = {
                        "type": "chat",
                        "id": player_id,
                        "name": players[player_id]["name"],
                        "message": message,
                        "color": players[player_id]["color"],
                    }

                    chat_history.append(entry)
                    del chat_history[:-100]

                    print(f"💬 {entry['name']}: {message}")
                    await broadcast(entry)

            except (json.JSONDecodeError, AttributeError, TypeError):
                print("⚠️ تم تجاهل رسالة غير صالحة")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.pop(websocket, None)
        info = players.pop(player_id, None)

        if info:
            await broadcast({"type": "left", "id": player_id})
            print(f"🔴 خرج {info['name']} | المتصلون: {len(players)}")
        else:
            print(f"🔴 انقطع اتصال لاعب | المتصلون: {len(clients)}")


async def main():
    async with websockets.serve(
        handle_client,
        "0.0.0.0",
        int(os.environ.get("PORT", "8765")),
        max_size=4096,
        ping_interval=20,
        ping_timeout=20,
    ):
        print(f"✅ سيرفر Super World يعمل على المنفذ {os.environ.get('PORT', '8765')}")
        print("👤 نظام اليوزرات والألوان وسجل آخر 100 رسالة جاهز")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nتم إيقاف السيرفر")
