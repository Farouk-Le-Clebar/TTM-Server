import asyncio
import websockets
from pymongo import MongoClient
import json
import uuid

client = MongoClient('mongodb://localhost:27017/')
db = client['game_database']
players_collection = db['players']

connected_clients = set()
client_states = {}

async def register(websocket):
    connected_clients.add(websocket)
    client_states[websocket] = {'isLogin': False}
    client_states[websocket]['uid'] = None

async def unregister(websocket):
    connected_clients.remove(websocket)
    if websocket in client_states:
        del client_states[websocket]

async def function_authentication(data_json, websocket):
    email = data_json.get('email')
    password = data_json.get('password')
    
    print(f"Email: {email}")
    print(f"Password: {password}")
    if email and password:
        existing_player = players_collection.find_one({'email': email})
        if existing_player:
            if existing_player['password'] == password:
                await websocket.send(json.dumps({'state': 'OK', 'uid': existing_player['uid']}))
                return True
            else:
                await websocket.send(json.dumps({'state': 'FAIL', 'message': 'Invalid password'}))
                return False
        else:
            uid = str(uuid.uuid4())
            player_data = {
                'email': email,
                'password': password,
                'uid': uid,
                'life': 100,
                'posX': 0.0,
                'posY': 0.0,
                'posZ': 0.0,
                'rotY': 0.0,
                'pocket': [["", 0, ""] for _ in range(5)],
                'weapon': [["", 0, ""] for _ in range(1)],
                'helmet': [["", 0, ""] for _ in range(1)],
                'armor': [["", 0, ""] for _ in range(1)],
                'eyes': [["", 0, ""] for _ in range(1)],
                'ears': [["", 0, ""] for _ in range(1)]
            }
            players_collection.insert_one(player_data)
            await websocket.send(json.dumps({'state': 'OK', 'uid': uid}))
            return True
    await websocket.send(json.dumps({'state': 'FAIL', 'message': 'Missing email or password'}))
    return False


async def function_new_player(data, websocket):
    uid = data.get('uid')
    if uid:
        player = players_collection.find_one({'uid': uid})
        if player:
            client_states[websocket]['isLogin'] = True
            client_states[websocket]['uid'] = uid
            message = json.dumps({'CMD': 'NP', 'uid': player['uid'], 'posX': player['posX'], 'posY': player['posY'], 'posZ': player['posZ'], 'rotY': player['rotY']})
            for ws in connected_clients:
                if ws != websocket and client_states[ws]['isLogin'] == True:
                    await ws.send(message)
                    player = players_collection.find_one({'uid': client_states[ws]['uid']})
                    messageNotif = json.dumps({'CMD': 'NP', 'uid': player['uid'], 'posX': player['posX'], 'posY': player['posY'], 'posZ': player['posZ'], 'rotY': player['rotY']})
                    await websocket.send(messageNotif)
            return True
    return False

async def function_deco_player(data, websocket):
    uid = data.get('uid')

    if uid:
        player = players_collection.find_one({'uid': uid})
        if player:
            message = json.dumps({'CMD': 'DP', 'uid': player['uid']})
            for ws in connected_clients:
                if ws != websocket and client_states[ws]['isLogin'] == True:
                    await ws.send(message)
            return True
    return False

async def function_get_position(data, websocket):
    uid = data.get('uid')
    if uid:
        player = players_collection.find_one({'uid': uid})
        if player:
            await websocket.send(json.dumps({'CMD': 'GP', 'posX': player['posX'], 'posY': player['posY'], 'posZ': player['posZ'], 'rotY': player['rotY']}))
        message = json.dumps({'CMD': 'PP', 'uid': player['uid'], 'posX': player['posX'], 'posY': player['posY'], 'posZ': player['posZ'], 'rotY': player['rotY']})
        for ws in connected_clients:
            if ws != websocket and client_states[ws]['isLogin'] == True:
                await ws.send(message)
            return True
    return False

async def function_player_position(data, websocket):
    uid = data.get('uid')
    if uid:
        player = players_collection.find_one({'uid': uid})
        if player:
            posX = data.get('posX')
            posY = data.get('posY')
            posZ = data.get('posZ')
            rotY = data.get('rotY')
            players_collection.update_one({'uid': uid}, {'$set': {'posX': posX, 'posY': posY, 'posZ': posZ, 'rotY': rotY}})
            message = json.dumps({'CMD': 'PP', 'uid': player['uid'], 'posX': player['posX'], 'posY': player['posY'], 'posZ': player['posZ'], 'rotY': player['rotY']})
            for ws in connected_clients:
                print(client_states[ws]['isLogin'])
                print(ws)
                print(websocket)
                if ws != websocket and client_states[ws]['isLogin'] == True:
                    print("Sending message")
                    await ws.send(message)
            return True
    return False

async def function_rotate_player(data, websocket):
    uid = data.get('uid')
    if uid:
        player = players_collection.find_one({'uid': uid})
        if player:
            print("Player found")
            rotY = data.get('rotY')
            players_collection.update_one({'uid': uid}, {'$set': {'rotY': rotY}})
            message = json.dumps({'CMD': 'ROT', 'uid': player['uid'], 'rotY': player['rotY']})
            for ws in connected_clients:
                if ws != websocket and client_states[ws]['isLogin'] == True:
                    await ws.send(message)
            return True
        print("Player not found")

async def function_hit_player(data, websocket):
    uid = data.get('uid')
    if uid:
        player = players_collection.find_one({'uid': uid})
        damage = data.get('damage')
        if player:
            player['life'] -= damage
            players_collection.update_one({'uid': uid}, {'$set': {'life': player['life']}})
            message = json.dumps({'CMD': 'HIT', 'life': player['life']})
            target_websocket = None
            for ws, state in client_states.items():
                if state.get('uid') == uid:
                    target_websocket = ws
                    break
            await target_websocket.send(message)
            if player['life'] <= 0:
                await respawn_player(player, target_websocket)
            return True

async def respawn_player(player, target_websocket):
    players_collection.update_many({'uid': player['uid']}, {'$set': {'life': 100, 'posX': 0.0, 'posY': 0.1, 'posZ': 0.0}})
    message = json.dumps({'CMD': 'PP', 'uid': player['uid'], 'posX': 0.0, 'posY': 0.1, 'posZ': 0.0, 'rotY': player['rotY']})
    for ws in connected_clients:
        if client_states[ws]['isLogin'] == True:
            await ws.send(message)
    message = json.dumps({'CMD': 'GP', 'posX': 0.0, 'posY': 0.1, 'posZ': 0.0, 'rotY': player['rotY']})
    await target_websocket.send(message)

async def function_get_inventory(data, websocket):
    uid = data.get('uid')
    if uid:
        player = players_collection.find_one({'uid': uid})
        if player:
            await websocket.send(json.dumps({'CMD': 'GI', 'pocket': player['pocket'], 'weapon': player['weapon'], 'helmet': player['helmet'], 'armor': player['armor'], 'eyes': player['eyes'], 'ears': player['ears']}))
            return True
    return False

async def function_grab_item_inventory(data, websocket):
    player_uid = data.get('uid')
    inventory_type = data.get('inventory')
    index = int(data.get('index'))

    if player_uid and inventory_type and index is not None:
        player = players_collection.find_one({'uid': player_uid})
        if player:
            inventory = player.get(inventory_type)
            if inventory and 0 <= index < len(inventory):
                inventory[index] = ["", 0, ""]
                players_collection.update_one({'uid': player_uid}, {'$set': {inventory_type: inventory}})
                return True
        else:
            print("Player not found")
    return False

async def function_drop_item_inventory(data, websocket):
    uid = data.get('uid')
    inventory_type = data.get('inventory')
    index = int(data.get('index'))
    quantity = int(data.get('quantity'))  # Convert quantity to int
    id_item = data.get('id')
    type_item = data.get('type')


    print(uid)
    player = players_collection.find_one({'uid': uid})
    if player:
        inventory = player.get(inventory_type)


        print(inventory)
        print(index)
        if inventory:
            current_item = inventory[index]
            # Ensure arithmetic operations are performed with integers
            if current_item[0] is None or current_item[0] == id_item:
                new_quantity = min(64, current_item[1] + quantity) if current_item[0] == id_item else quantity
                inventory[index] = [id_item, new_quantity, type_item]
            else:
                inventory[index] = [id_item, quantity, type_item]
            players_collection.update_one({'uid': uid}, {'$set': {inventory_type: inventory}})
            print("player inventory updated")
            print(player)
            return True
        else:
            print("player inventory not updated")
    print("player not found")
    return False

async def function_handler(data, websocket):
    data_json = json.loads(data)
    cmd = data_json.get('CMD')

    print(f"Command: {cmd}")
    if cmd == 'AUTH':
        if await function_authentication(data_json, websocket) == True:
            return 0
    if cmd == 'GP':
        if await function_get_position(data_json, websocket) == True:
            return 0
    if cmd == 'PP':
        if await function_player_position(data_json, websocket) == True:
            return 0
    if cmd == 'NP':
        if await function_new_player(data_json, websocket) == True:
            return 0
    if cmd == 'DP':
        if await function_deco_player(data_json, websocket) == True:
            return 0
    if cmd == 'ROT':
        if await function_rotate_player(data_json, websocket) == True:
            return 0 
    if cmd == 'HIT':
        if await function_hit_player(data_json, websocket) == True:
            return 0
    if cmd == 'GI':
        if await function_get_inventory(data_json, websocket) == True:
            return 0 
    if cmd == 'GRABITEM':
        if await function_grab_item_inventory(data_json, websocket) == True:
            return 0
    if cmd == 'DROPITEM':
        if await function_drop_item_inventory(data_json, websocket) == True:
            return 0 

async def handler(websocket, path):
    await register(websocket)
    try:
        while True:
            data = await websocket.recv()
            print(f"Received data: {data}")

            await function_handler(data, websocket)
                
    except websockets.exceptions.ConnectionClosed:
        print("Connection closed")
    finally:
        await unregister(websocket)

def display_players():
    players = players_collection.find()
    for player in players:
        print(player)

start_server = websockets.serve(handler, "localhost", 8765)

asyncio.get_event_loop().run_until_complete(start_server)
print("WebSocket server started on ws://localhost:8765")

display_players()

asyncio.get_event_loop().run_forever()
