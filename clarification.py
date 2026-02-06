# clarification.py
from llm_client import _safe_call
import json

def needs_clarification_llm(query: str):
    system = """
You are an AI shopping assistant.

If the user input is ambiguous and cannot be searched directly,
ask a clarification question.

Examples:
"I like red" → ask "Red what?"
"Something nice" → ask product type
"Red kurti under 1500" → clear

Return ONLY JSON:
{
  "needs_clarification": true/false,
  "question": ""
}
"""
    res = _safe_call(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": query}
        ],
        max_tokens=80,
        temp=0
    )

    try:
        return json.loads(res)
    except:
        return {"needs_clarification": False, "question": ""}
