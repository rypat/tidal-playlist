from flask import Flask, request, jsonify, render_template_string
import os
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
import tidalapi
import json
import requests
import time
from pathlib import Path

app = Flask(__name__)

SESSION_FILE = Path("tidal_session.json")

def get_session():
	session = tidalapi.Session()
	if SESSION_FILE.exists():
		data = json.loads(SESSION_FILE.read_text())
		session.load_oauth_session(
			data["token_type"],
			data["access_token"],
			data["refresh_token"]
		)
	return session if session.check_login() else None

HTML = """
<!DOCTYPE html>
<html>
<head>
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>Playlist Generator</title>
	<style>
		* { box-sizing: border-box; margin: 0; padding: 0; }
		body { font-family: -apple-system, sans-serif; background: #0f0f0f; color: #f0f0f0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; }
		.container { width: 100%; max-width: 480px; }
		h1 { font-size: 18px; font-weight: 500; letter-spacing: 0.05em; margin-bottom: 32px; color: #888; text-transform: uppercase; }
		label { display: block; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: #555; margin-bottom: 8px; }
		input, textarea, select { width: 100%; background: #1a1a1a; border: 1px solid #2a2a2a; color: #f0f0f0; padding: 12px; font-size: 15px; border-radius: 4px; margin-bottom: 20px; outline: none; font-family: inherit; }
		input:focus, textarea:focus, select:focus { border-color: #444; }
		textarea { resize: none; height: 80px; }
		button { width: 100%; background: #f0f0f0; color: #0f0f0f; border: none; padding: 14px; font-size: 14px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; border-radius: 4px; cursor: pointer; }
		button:disabled { background: #2a2a2a; color: #444; cursor: not-allowed; }
		#results { margin-top: 28px; }
		.track { font-size: 14px; color: #aaa; padding: 8px 0; border-bottom: 1px solid #1a1a1a; }
		.track span { color: #f0f0f0; }
		.status { font-size: 13px; color: #555; margin-bottom: 16px; letter-spacing: 0.03em; }
		.error { color: #e05555; font-size: 13px; margin-top: 16px; }
	</style>
</head>
<body>
<div class="container">
	<h1>Playlist Generator</h1>

	<label>New or existing playlist?</label>
	<select id="mode">
		<option value="new">Create new</option>
		<option value="existing">Add to existing</option>
	</select>

	<label id="playlist-label">Playlist name</label>
	<input type="text" id="playlist-name" placeholder="e.g. sunday soul">

	<label>Describe the vibe</label>
	<textarea id="vibe" placeholder="e.g. warm classic soul, Sunday morning feeling, like Al Green and Bill Withers"></textarea>

	<button id="btn" onclick="generate()">Generate</button>

	<div id="results"></div>
</div>

<script>
	document.getElementById("mode").addEventListener("change", function() {
		const label = document.getElementById("playlist-label");
		const input = document.getElementById("playlist-name");
		if (this.value === "existing") {
			label.textContent = "Search playlist by name";
			input.placeholder = "e.g. sunday";
		} else {
			label.textContent = "Playlist name";
			input.placeholder = "e.g. sunday soul";
		}
	});

	async function generate() {
		const mode = document.getElementById("mode").value;
		const name = document.getElementById("playlist-name").value.trim();
		const vibe = document.getElementById("vibe").value.trim();
		const btn = document.getElementById("btn");
		const results = document.getElementById("results");

		if (!name || !vibe) {
			results.innerHTML = '<div class="error">Please fill in all fields.</div>';
			return;
		}

		btn.disabled = true;
		btn.textContent = "Generating...";
		results.innerHTML = '<div class="status">Asking Claude for tracks...</div>';

		try {
			const response = await fetch("/generate", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ mode, name, vibe })
			});

			const reader = response.body.getReader();
			const decoder = new TextDecoder();
			results.innerHTML = "";

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;
				const lines = decoder.decode(value).split("\\n").filter(Boolean);
				for (const line of lines) {
					const data = JSON.parse(line);
					if (data.type === "status") {
						results.innerHTML += `<div class="status">${data.message}</div>`;
					} else if (data.type === "track") {
						results.innerHTML += `<div class="track"><span>${data.track}</span> — ${data.artist}</div>`;
					} else if (data.type === "notfound") {
						results.innerHTML += `<div class="track" style="color:#444">Not found: ${data.track}</div>`;
					} else if (data.type === "done") {
						results.innerHTML += `<div class="status" style="margin-top:16px;color:#888">${data.message}</div>`;
					} else if (data.type === "error") {
						results.innerHTML += `<div class="error">${data.message}</div>`;
					}
				}
			}
		} catch (e) {
			results.innerHTML = '<div class="error">Something went wrong. Try again.</div>';
		}

		btn.disabled = false;
		btn.textContent = "Generate";
	}
</script>
</body>
</html>
"""

@app.route("/")
def index():
	return render_template_string(HTML)

@app.route("/generate", methods=["POST"])
def generate():
	data = request.json
	mode = data.get("mode")
	name = data.get("name")
	vibe = data.get("vibe")

	def stream():
		session = get_session()
		if not session:
			yield json.dumps({"type": "error", "message": "Tidal session expired. Run login.py on your PC."}) + "\n"
			return

		# Find or create playlist
		if mode == "existing":
			yield json.dumps({"type": "status", "message": "Searching your playlists..."}) + "\n"
			user_playlists = session.user.playlists()
			matches = [p for p in user_playlists if name.lower() in p.name.lower()]
			if not matches:
				yield json.dumps({"type": "error", "message": f"No playlist found matching '{name}'"}) + "\n"
				return
			playlist = matches[0]
			yield json.dumps({"type": "status", "message": f"Found: {playlist.name}"}) + "\n"
		else:
			playlist = session.user.create_playlist(name, vibe)
			yield json.dumps({"type": "status", "message": f"Created playlist: {playlist.name}"}) + "\n"

		# Ask Claude
		yield json.dumps({"type": "status", "message": "Asking Claude for tracks..."}) + "\n"

		response = requests.post(
			"https://api.anthropic.com/v1/messages",
			headers={
				"x-api-key": ANTHROPIC_API_KEY,
				"anthropic-version": "2023-06-01",
				"content-type": "application/json"
			},
			json={
				"model": "claude-sonnet-4-5",
				"max_tokens": 1000,
				"messages": [{
					"role": "user",
					"content": f"Generate a playlist for this vibe: {vibe}. Return ONLY a JSON array of 25 objects, each with 'track' and 'artist' keys. No other text, no markdown."
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
				time.sleep(2)
				yield json.dumps({"type": "track", "track": track.name, "artist": track.artist.name}) + "\n"
				found += 1
			else:
				yield json.dumps({"type": "notfound", "track": item["track"]}) + "\n"

		yield json.dumps({"type": "done", "message": f"Done — {found}/25 tracks added to '{playlist.name}'"}) + "\n"

	return app.response_class(stream(), mimetype="application/json")

if __name__ == "__main__":
	app.run(debug=True)