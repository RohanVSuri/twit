"""
LLM prompt templates for the tweet digest pipeline.
All prompts target claude-haiku-4-5-20251001.
"""

SUMMARIZE_CLUSTER_PROMPT = """
You are a news editor writing a briefing from a cluster of tweets on a related topic.

Here are the tweets (format: [ID] text):
{tweet_list}

Your task:
1. Write a short category label (2–4 words, e.g. "Startups & VC", "Tennis", "AI Research")

2. Write a 3–5 sentence summary covering only the most important developments. This is the top-line brief a reader sees first — focus on significance, not completeness.

3. Write one bullet per distinct real-world event or development.

   Critical rules:
   - Write each bullet as a NEWS FACT, not a tweet summary. Bad: "@KobeissiLetter says oil hit $99." Good: "Oil surged above $99/barrel, up ~10% on the week."
   - SYNTHESIZE across tweets — multiple tweets often cover the same event from different angles. Combine them into one bullet with the best details from each.
   - One bullet = one event. Do not create separate bullets for tweets that are about the same thing.
   - Be specific: include names, numbers, prices, companies, outcomes wherever the tweets provide them.
   - Specificity test: every tweet ID you cite must contribute at least one concrete named detail to the bullet (a name, number, location, or outcome). If a tweet only adds vague sentiment or restates the same fact, omit it from source_ids. If tweets cover meaningfully different aspects of the same event (e.g. the initial incident vs. the government response), write separate focused bullets rather than merging into one vague one.
   - Do not invent or infer details not present in the tweets.
   - Skip pure opinions, reactions, and commentary unless they are themselves the news (e.g. a notable figure making a notable claim).
   - 1–2 sentences per bullet. As many bullets as there are genuinely distinct events.
   - List all tweet IDs that contributed to each bullet.
   - Events with a higher combined_importance score and more tweets covering them are more significant — bullet those first.

Respond in this exact JSON format:
{{"label": "Category Name", "summary": "3–5 sentence overview of the most important news.", "bullets": [{{"text": "Synthesized fact.", "source_ids": ["id1", "id2"]}}, {{"text": "Another event.", "source_ids": ["id3"]}}]}}

Respond with JSON only. No preamble, no markdown fences.
"""

MERGE_CLUSTERS_PROMPT = """
Here is a list of topic cluster labels discovered from today's tweets:
{label_list}

Identify any clusters that should be merged because they are clearly the same topic or closely related sub-topics.

Respond in this exact JSON format:
{{
  "merges": [
    {{"into": "Final Label", "merge": ["Label A", "Label B"]}},
    {{"into": "Another Label", "merge": ["Label C", "Label D"]}}
  ]
}}

Only suggest merges where you are confident. If no merges are needed, return: {{"merges": []}}
Respond with JSON only. No preamble, no markdown fences.
"""

RAG_CHAT_PROMPT = """
You are answering a question about today's tweets. Use only the tweets provided below as your source of truth.

Today's date: {date}

Relevant tweets (format: [ID | URL] text):
{tweet_list}

User question: {question}

Instructions:
- Answer based only on the tweets above. Do not use outside knowledge.
- If the tweets don't contain enough information to answer, say so clearly.
- Be specific: mention names, numbers, and details from the tweets.
- After your answer, list the URLs of the tweets you drew from as citations.
- Keep your answer concise (3–6 sentences unless the question warrants more).
"""

EMOJI_PROMPT = """
Assign a single relevant emoji to each of these topic category labels.

Labels: {label_list}

Respond in JSON format:
{{"Label Name": "emoji", "Another Label": "emoji"}}

Respond with JSON only.
"""
