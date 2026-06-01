import tidalapi
import json
import requests
import time
from pathlib import Path

SESSION_FILE = Path("tidal_session.json")

# Load saved session
session = tidalapi.Session()
data = json.loads(SESSION_FILE.read_text())
session.load_oauth_session(
	data["token_type"],
	data["access_token"],
	data["refresh_token"]
)

if not session.check_login():
	print("Session expired. Run login.py again.")
	exit()

# New or existing playlist
mode = input("Create new or add to existing? (new/existing): ").strip().lower()

if mode == "existing":
	search_term = input("Search your playlists: ").strip().lower()
	user_playlists = session.user.playlists()
	matches = [p for p in user_playlists if search_term in p.name.lower()]

	if not matches:
		print("No playlists found matching that name.")
		exit()
	elif len(matches) == 1:
		playlist = matches[0]
		print(f"Found: {playlist.name}")
	else:
		print("Multiple matches found:")
		for i, p in enumerate(matches):
			print(f"{i+1}. {p.name}")
		choice = int(input("Choose a number: ")) - 1
		playlist = matches[choice]

elif mode == "new":
	playlist_name = input("Name your playlist: ").strip()
	playlist = session.user.create_playlist(playlist_name, "")
	print(f"Created: {playlist.name}")

else:
	print("Please type 'new' or 'existing'.")
	exit()

# Ask Claude for tracks
vibe = input("Describe the vibe: ").strip()

response = requests.post(
	"https://api.anthropic.com/v1/messages",
	headers={
		"x-api-key": "",
		"anthropic-version": "2023-06-01",
		"content-type": "application/json"
	},
	json={
		"model": "claude-sonnet-4-5",
		"max_tokens": 1000,
		"messages": [{
			"role": "user",
			"content": f"Generate a playlist for this vibe: {vibe}. Return ONLY a JSON array of 10 objects, each with 'track' and 'artist' keys. No other text, no markdown."
		}]
	}
)

raw = response.json()["content"][0]["text"]
raw = raw.replace("```json", "").replace("```", "").strip()
tracks = json.loads(raw)

# Add tracks
found = 0
for item in tracks:
	results = session.search(f"{item['track']} {item['artist']}", models=[tidalapi.Track])
	if results["tracks"]:
		track = results["tracks"][0]
		playlist.add([track.id])
		time.sleep(1)
		print(f"Added: {track.name} — {track.artist.name}")
		found += 1
	else:
		print(f"Not found: {item['track']} — {item['artist']}")

print(f"\nDone! {found}/10 tracks added to '{playlist.name}' on Tidal.")