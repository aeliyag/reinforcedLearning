import React, { useEffect, useRef, useState } from "react";

type MasteryMap = Record<string, number>; // 0..2
type NextResp = {
  action: string;
  target: { letter: string; list?: string[] };
  state_key: string;
};

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

const API = "http://localhost:8000"; // adjust to your backend

export default function AlphabetAdaptive() {
  const [current, setCurrent] = useState<string>("A");
  const [masteryLevel, setMasteryLevel] = useState<number>(0);
  const [masteryMap, setMasteryMap] = useState<MasteryMap>(
    Object.fromEntries(LETTERS.map(l => [l, 0]))
  );
  const [recent, setRecent] = useState<string[]>([]);
  const stateKeyRef = useRef<string>("A:0");
  const [pending, setPending] = useState<boolean>(false);
  const [msg, setMsg] = useState<string>("");

  // Request next recommendation
  async function getNext() {
    setPending(true);
    const body = {
      current_letter: current,
      mastery_level: masteryLevel,
      mastery_map: masteryMap,
      recent_history: recent.slice(-5)
    };
    const res = await fetch(`${API}/alphabet/next`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const data: NextResp = await res.json();
    stateKeyRef.current = data.state_key;

    // Decide next letter to display
    const nextLetter = data.target.letter || current;
    setMsg(`Action: ${data.action}`);
    setCurrent(nextLetter);
    // masteryLevel stays; will change after feedback below
    setPending(false);
  }

  // Simulated scoring (replace with your real ASL scoring)
  function scoreAttempt(): { reward: number; correct: boolean } {
    // stub: random-ish with slight boost for higher mastery
    const p = 0.45 + masteryLevel * 0.25; // 0.45, 0.7, 0.95
    const correct = Math.random() < Math.min(p, 0.98);
    const reward = correct ? 1 : -1;
    return { reward, correct };
  }

  async function submitFeedback(correct: boolean, reward: number) {
    // update mastery heuristics client-side
    const nextMastery =
      correct
        ? Math.min(2, masteryLevel + 1)
        : Math.max(0, masteryLevel - 0); // keep same on fail for simplicity

    const nextMap = { ...masteryMap, [current]: nextMastery };
    setMasteryMap(nextMap);
    setMasteryLevel(nextMastery);
    setRecent([...recent, current].slice(-8));

    const payload = {
      state_key: stateKeyRef.current,
      action: msg.replace("Action: ", "") || "practice_current",
      reward,
      next_state: { letter: current, mastery_level: nextMastery }
    };

    await fetch(`${API}/alphabet/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  }

  // Handlers for a single attempt cycle
  async function handleAttempt() {
    if (pending) return;
    const { reward, correct } = scoreAttempt();
    await submitFeedback(correct, reward);
    await getNext();
  }

  // Fallback guardrails (while RL is learning)
  useEffect(() => {
    // auto-advance if letter is clearly mastered
    if (masteryMap[current] >= 2) {
      const idx = LETTERS.indexOf(current);
      const next = LETTERS[Math.min(idx + 1, LETTERS.length - 1)];
      if (next !== current) setCurrent(next);
    }
  }, [current, masteryMap]);

  // Initial recommendation
  useEffect(() => {
    getNext(); // on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="p-4 max-w-xl mx-auto space-y-4 border rounded-lg">
      <h2 className="text-xl font-semibold">ASL Alphabet — Adaptive Mode</h2>

      <div className="p-3 border rounded">
        <div className="text-sm text-gray-600">Current Letter</div>
        <div className="text-5xl font-bold tracking-widest">{current}</div>
        <div className="text-sm mt-2">
          Mastery: {["Unseen","Practicing","Mastered"][masteryMap[current] || 0]}
        </div>
        <div className="text-xs text-gray-500">{msg}</div>
      </div>

      {/* Replace this block with your real player/camera UI */}
      <div className="p-3 border rounded">
        <div className="mb-2">Simulate attempt (wire to your scoring):</div>
        <button
          onClick={handleAttempt}
          disabled={pending}
          className="px-3 py-2 rounded bg-black text-white"
        >
          Submit Attempt
        </button>
      </div>

      <div className="text-xs text-gray-500">
        Tip: This stub randomly scores attempts but weights by mastery.
        Replace <code>scoreAttempt()</code> with your ASL model’s score and pass its
        result as reward: <code>+1</code> correct, <code>0</code> partial, <code>-1</code> incorrect.
      </div>
    </div>
  );
}
