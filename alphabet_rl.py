# alphabet_rl.py

from flask import Flask, request, jsonify
from flask_cors import CORS
import json, os, string, random
from collections import defaultdict

app = Flask(__name__)
CORS(app)

LETTERS = list(string.ascii_uppercase)  # A..Z
Q_PATH = os.environ.get("Q_PATH", "q_table.json")

# Q-table: { "state_key": {"action": q_value, ...}, ... }
Q = defaultdict(dict)

ALPHA = 0.5   # learning rate
GAMMA = 0.9   # discount
EPSILON = 0.15  # exploration
MIN_RECENT_FOR_REVIEW = 2
PREFER_MOVE_ON_AT_ML = 1   # when mastery_level >= 1, prefer moving next

ACTIONS = [
    "practice_current",
    "move_next",
    "jump_trouble",
    "review_recent"
]

def load_q():
    global Q
    if os.path.exists(Q_PATH):
        with open(Q_PATH, "r") as f:
            raw = json.load(f)
            Q = defaultdict(dict, raw)

def save_q():
    with open(Q_PATH, "w") as f:
        json.dump(Q, f)

def state_key(letter: str, mastery_level: int) -> str:
    return f"{letter}:{mastery_level}"

def argmax_action(skey: str):
    if skey not in Q or not Q[skey]:
        return random.choice(ACTIONS)
    return max(Q[skey].items(), key=lambda kv: kv[1])[0]



def epsilon_greedy(skey: str):
    if random.random() < EPSILON:
        return random.choice(ACTIONS)
    return argmax_action(skey)

def update_q(skey: str, action: str, reward: float, next_skey: str):
    old_q = Q[skey].get(action, 0.0)
    next_max = max(Q[next_skey].values(), default=0.0)
    new_q = old_q + ALPHA * (reward + GAMMA * next_max - old_q)
    Q[skey][action] = new_q
    save_q()

def next_letter(letter: str):
    idx = LETTERS.index(letter)
    return LETTERS[min(idx + 1, len(LETTERS) - 1)]

def pick_trouble_letter(mastery_map):
    # mastery_map: {"A":0..2, ...}; choose lowest mastery with most errors
    trouble = [l for l, m in mastery_map.items() if m == 0]
    if not trouble:
        trouble = [l for l, m in mastery_map.items() if m == 1]
    return random.choice(trouble) if trouble else None

@app.route("/alphabet/next", methods=["POST"])
def api_next():
    """
    Input JSON:
    {
      "current_letter": "C",
      "mastery_level": 0,              # 0=unseen,1=practicing,2=mastered
      "mastery_map": {"A":2,"B":1,...},# optional, guides jump/review
      "recent_history": ["A","B","B"]  # optional, for review_recent
    }
    """
    load_q()
    data = request.get_json(force=True)
    letter = data["current_letter"]
    ml = int(data.get("mastery_level", 0))
    mastery_map = data.get("mastery_map", {})
    recent = data.get("recent_history", [])

    skey = state_key(letter, ml)
    action = epsilon_greedy(skey)

    # Compute a concrete recommendation payload
    target = {"letter": letter, "list": []}

    if action == "practice_current":
        target["letter"] = letter

    elif action == "move_next":
        target["letter"] = next_letter(letter)

    elif action == "jump_trouble":
        t = pick_trouble_letter(mastery_map) if mastery_map else None
        target["letter"] = t or letter

    elif action == "review_recent":
        # last up to 3 distinct recent letters, fallback to current
        seen = []
        for l in reversed(recent):
            if l not in seen:
                seen.append(l)
            if len(seen) == 3:
                break
        target["list"] = seen or [letter]
        target["letter"] = (seen[-1] if seen else letter)

    return jsonify({"action": action, "target": target, "state_key": skey})

@app.route("/alphabet/feedback", methods=["POST"])
def api_feedback():
    """
    Input JSON:
    {
      "state_key": "C:0",
      "action": "practice_current",
      "reward": 1,                 # +1 correct, 0 partial/skip, -1 incorrect
      "next_state": { "letter":"C", "mastery_level": 1 }
    }
    """
    load_q()
    data = request.get_json(force=True)
    skey = data["state_key"]
    action = data["action"]
    reward = float(data["reward"])
    next_letter_ = data["next_state"]["letter"]
    next_ml = int(data["next_state"]["mastery_level"])
    next_skey = state_key(next_letter_, next_ml)

    update_q(skey, action, reward, next_skey)
    return jsonify({"ok": True})

@app.get("/")
def health():
    return {"ok": True, "service": "alphabet-rl"}


if __name__ == "__main__":
    load_q()
    app.run(host="0.0.0.0", port=8000, debug=True)
