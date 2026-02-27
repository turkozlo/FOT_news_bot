import json
from pathlib import Path

print("[SUMMARIZER MODULE] summarizer.py загружен")

with open("config/prompts.json", "r", encoding="utf-8-sig") as f:
    PROMPTS = json.load(f)

with open("config/llm_config.json", "r", encoding="utf-8-sig") as f:
    llm_conf = json.load(f)

llm_backend = llm_conf.get("llm_backend", 2)

if llm_backend == 0:
    print("Используется OpenAI")
    from openai import OpenAI
    client = OpenAI(
        base_url=llm_conf["base_url_Open_AI"],
        api_key=llm_conf["api_key_Open_AI"],
    )
elif llm_backend == 1:
    print("Используется LangChain+Groq")
    from langchain_groq import ChatGroq
    from langchain_core.messages import HumanMessage
    client = ChatGroq(
        model=llm_conf.get("model_LANGCHAIN", "llama3-8b-8192"),
        api_key=llm_conf["api_key_LANGCHAIN"]
    )
else:
    print("Используется LangChain+Mistral")
    from langchain_mistralai import ChatMistralAI
    from langchain_core.messages import HumanMessage

    client = ChatMistralAI(
        model_name=llm_conf.get("model_LANGCHAIN_mistral", "mistral-medium-latest"),
        api_key=llm_conf["api_key_LANGCHAIN_mistral"]
    )

import asyncio
from src.llm_classifier import llm_semaphore

def summarize_text(text: str, department: str = "") -> str:
    # Оставляем синхронную обертку для совместимости, если нужно, 
    # но лучше переименовать в async или сделать так:
    pass

async def summarize_text(text: str, department: str = "") -> str:
    if not department:
        return ""
    prompt = PROMPTS["summary"].format(department=department, text=text)
    print("[SUMMARIZER] Prompt сформирован")
    
    max_retries = 5
    current_delay = 2.0
    
    async with llm_semaphore:
        for attempt in range(max_retries + 1):
            try:
                if llm_backend == 0:
                    response = client.chat.completions.create(
                        model=llm_conf["model_Open_AI"],
                        extra_body={},
                        messages=[{"role": "user", "content": prompt}],
                    )
                    summary = response.choices[0].message.content.strip()
                else:
                    res = await client.ainvoke([HumanMessage(content=prompt)])
                    summary = res.content.strip()

                await asyncio.sleep(1.2)
                print(f"[SUMMARIZER] Готовое резюме: {summary}")
                return summary
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate" in error_str.lower():
                    if attempt < max_retries:
                        print(f"[SUMMARIZER] Rate limit (429). Retrying in {current_delay}s... (Attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(current_delay)
                        current_delay *= 2
                        continue
                print(f"[SUMMARIZER ERROR] {e}")
                return ""
    
    return ""