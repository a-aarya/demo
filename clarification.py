# clarification.py

from llm_client import _safe_call
import json


def check_clarification(query: str):
    """
    Decides if query is clear enough to search.

    Returns dict:
    {
      "needs_clarification": bool,
      "question": str,
      "final_query": str
    }
    """

    system_prompt = """
You are an AI fashion shopping assistant.

If the user query is too vague to search products,
ask a clarification question.

Examples:
"green" → ask what product (kurta, saree, lehenga)
"wedding outfit" → ask product type
"red nike shoes" → clear, no clarification

Return ONLY JSON:
{
 "needs_clarification": true/false,
 "question": "",
 "final_query": ""
}
"""

    res = _safe_call(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        max_tokens=120,
        temp=0.0,
    )

    try:
        return json.loads(res)
    except:
        return {
            "needs_clarification": False,
            "question": "",
            "final_query": query
        }
