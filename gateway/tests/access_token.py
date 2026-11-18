"""Print an access token of the local Keycloak for a demo user: python3 -I gateway/tests/access_token.py alice."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_e2e import token  # noqa: E402

if __name__ == "__main__":
    print(token(sys.argv[1] if len(sys.argv) > 1 else "alice"))
