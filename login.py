import tidalapi
import json
from pathlib import Path

SESSION_FILE = Path("tidal_session.json")

session = tidalapi.Session()

if SESSION_FILE.exists():
    data = json.loads(SESSION_FILE.read_text())
    session.load_oauth_session(
        data["token_type"],
        data["access_token"],
        data["refresh_token"]
    )

if not session.check_login():
    login, future = session.login_oauth()
    print(f"\nOpen this URL in your browser:\nhttps://{login.verification_uri_complete}\n")
    print("Waiting for you to log in...")
    future.result()

    SESSION_FILE.write_text(json.dumps({
        "token_type": session.token_type,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token
    }))

print("Logged in successfully!")