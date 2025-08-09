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
def is_mastered(ltr, mastery_map):
    return mastery_map.get(ltr, 0) >= 2


def save_q():
    with open(Q_PATH, "w") as f:
        json.dump(Q, f)

def state_key(letter: str, mastery_level: int) -> str:
    return f"{letter}:{mastery_level}"


def heuristic_policy(letter, ml, mastery_map, recent):
    # If mastered, definitely move on
    if ml >= 2:
        return "move_next"
    # Prefer moving on once practicing starts
    if ml >= PREFER_MOVE_ON_AT_ML:
        return "move_next"
    # If there are true trouble letters, jump to one
    t = pick_trouble_letter(mastery_map, letter) if mastery_map else None
    if t and t != letter:
        return "jump_trouble"
    # If there’s enough recent material (non-mastered), review it
    if recent:
        recent_unmastered = [r for r in set(recent) if not is_mastered(r, mastery_map)]
        if len(recent_unmastered) >= MIN_RECENT_FOR_REVIEW:
            return "review_recent"
    # Otherwise, practice current
    return "practice_current"


def argmax_action(skey: str):
    # If we have nothing learned for this state yet, defer to heuristic instead of random
    if skey not in Q or not Q[skey]:
        return None  # signal "no learned action"
    return max(Q[skey].items(), key=lambda kv: kv[1])[0]

def epsilon_greedy(skey: str, letter, ml, mastery_map, recent):
    learned_best = argmax_action(skey)
    if learned_best is None:
        # Cold-start: use heuristic, not random
        base = heuristic_policy(letter, ml, mastery_map, recent)
        # Still allow a *bit* of exploration if you want:
        return random.choice(ACTIONS) if random.random() < EPSILON else base
    # We have learned values; do normal epsilon-greedy
    return random.choice(ACTIONS) if random.random() < EPSILON else learned_best


def update_q(skey: str, action: str, reward: float, next_skey: str):
    old_q = Q[skey].get(action, 0.0)
    next_max = max(Q[next_skey].values(), default=0.0)
    new_q = old_q + ALPHA * (reward + GAMMA * next_max - old_q)
    Q[skey][action] = new_q
    save_q()

def next_letter(letter: str, mastery_map=None):
    idx = LETTERS.index(letter)
    # Try to find the next letter that is not mastered
    if mastery_map:
        n = len(LETTERS)
        for step in range(1, n+1):
            cand = LETTERS[(idx + step) % n]
            if mastery_map.get(cand, 0) < 2:
                return cand
    # Fallback: wrap
    return LETTERS[(idx + 1) % len(LETTERS)]


def pick_trouble_letter(mastery_map, current_letter):
    # prefer mastery 0, then 1
    candidates = [l for l, m in mastery_map.items() if m == 0] or \
                 [l for l, m in mastery_map.items() if m == 1]
    if not candidates:
        return None
    # choose the nearest in alphabet distance to current
    cidx = LETTERS.index(current_letter)
    return min(candidates, key=lambda l: abs(LETTERS.index(l) - cidx))


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
    # 🚫 Skip mastered letters
    if mastery_map.get(letter, 0) >= 2:
        letter = next_letter(letter, mastery_map)
        ml = mastery_map.get(letter, 0)

    skey = state_key(letter, ml)
    action = epsilon_greedy(skey, letter, ml, mastery_map, recent)


    # Compute a concrete recommendation payload
    target = {"letter": letter, "list": []}

    if action == "practice_current":
        target["letter"] = letter

    elif action == "move_next":
        target["letter"] = next_letter(letter, mastery_map)

    elif action == "jump_trouble":
        t = pick_trouble_letter(mastery_map, letter) if mastery_map else None
        target["letter"] = t or letter


    elif action == "review_recent":
        # last up to 3 distinct *unmastered* recent letters (most-recent first)
        seen = []
        for l in reversed(recent):
            if l not in seen and not is_mastered(l, mastery_map):
                seen.append(l)
            if len(seen) == 3:
                break
        if not seen:
            # nothing to review—move on
            action = "move_next"
            target["letter"] = next_letter(letter, mastery_map)
            target["list"] = []
        else:
            target["list"] = seen
            target["letter"] = seen[0]  # most recent unique, unmastered

    if is_mastered(target["letter"], mastery_map):
        target["letter"] = next_letter(letter, mastery_map)
    if target.get("list"):
        target["list"] = [l for l in target["list"] if not is_mastered(l, mastery_map)]
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
